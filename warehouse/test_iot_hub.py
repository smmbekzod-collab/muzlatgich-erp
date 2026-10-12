"""Offline regression tests; never contact devices or Telegram."""
import json
from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth.hashers import make_password
from core.models import Organization, Facility, Camera, Membership
from .iot_models import IoTGateway, IoTDevice, IoTReceipt
from .models import CameraEnvironmentReading


@override_settings(STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class IoTHubTests(TestCase):
    def setUp(self):
        U=get_user_model()
        self.admin=U.objects.create_user('iot_owner',password='TestPass12345!',is_staff=True)
        self.admin_b=U.objects.create_user('iot_other',password='TestPass12345!',is_staff=True)
        self.o=Organization.objects.create(name='Site A',code='iot-a',camera_limit=25)
        self.b=Organization.objects.create(name='Site B',code='iot-b',camera_limit=25)
        self.f=Facility.objects.create(organization=self.o,code='main',name='Site A main')
        self.fb=Facility.objects.create(organization=self.b,code='main',name='Site B main')
        self.cameras=[
            Camera.objects.create(organization=self.o,facility=self.f,number=i)
            for i in range(1,26)]
        self.cb=Camera.objects.create(organization=self.b,facility=self.fb,number=1)
        Membership.objects.create(user=self.admin,organization=self.o,
            role='admin',all_cameras=True,all_facilities=True)
        Membership.objects.create(user=self.admin_b,organization=self.b,
            role='admin',all_cameras=True,all_facilities=True)
        self.secret='secret-very-long-and-unguessable-abcdef1234567890'
        self.ga=IoTGateway.objects.create(organization=self.o,facility=self.f,
            name='Gateway 1',created_by=self.admin,
            transport='rs485',secret_hash=make_password(self.secret))
        self.gb=IoTGateway.objects.create(organization=self.b,facility=self.fb,
            name='Gateway B',created_by=self.admin_b,
            transport='rs485',secret_hash=make_password('different-secret-very-long-4567890'))
        self.sensors=[
            IoTDevice.objects.create(gateway=self.ga,camera=cam,code=f's{i:02d}',
                name=f'Sensor {i}',address=i)
            for i,cam in enumerate(self.cameras,1)]
        self.sb=IoTDevice.objects.create(gateway=self.gb,camera=self.cb,
            code='b01',name='Other sensor',address=1)
        self.url=reverse('iot_readings')
        self.auth={'HTTP_AUTHORIZATION':f'Bearer {self.ga.pk}.{self.secret}'}

    def item(self,index=0,**overrides):
        obj={
            'device_code':self.sensors[index].code,
            'event_id':f'unique-event-{index}',
            'measured_at':timezone.now().isoformat(),
            'temperature':'1.5','humidity':'85'
        }
        obj.update(overrides)
        return obj

    def send(self, items, **extra):
        return self.client.post(self.url,
            data=json.dumps({'readings':items}),content_type='application/json',
            **(extra or self.auth))

    @patch('warehouse.iot_api.reconcile_camera')
    def test_25_cameras_batch_replay_and_no_duplicate_alerts(self,reconcile):
        items=[self.item(index=i) for i in range(25)]
        with self.captureOnCommitCallbacks(execute=True):
            r=self.send(items)
        self.assertEqual(r.status_code,200,r.content)
        self.assertEqual(r.json()['inserted'],25)
        self.assertEqual(CameraEnvironmentReading.objects.count(),25)
        self.assertEqual(IoTReceipt.objects.count(),25)
        self.assertEqual(reconcile.call_count,25)
        with self.captureOnCommitCallbacks(execute=True):
            replay=self.send(items)
        self.assertEqual(replay.status_code,200,replay.content)
        self.assertEqual(replay.json()['duplicates'],25)
        self.assertEqual(IoTReceipt.objects.count(),25)
        self.assertEqual(CameraEnvironmentReading.objects.count(),25)
        self.assertEqual(reconcile.call_count,25)

    def test_forged_cross_organization_device_rejected(self):
        response=self.send([self.item(device_code='b01')])
        self.assertEqual(response.status_code,400)
        self.assertEqual(CameraEnvironmentReading.objects.count(),0)

    def test_wrong_secret_and_anonymous_denied(self):
        self.assertEqual(self.send([self.item()],HTTP_AUTHORIZATION='Bearer invalid').status_code,401)
        self.assertEqual(self.client.post(self.url,
            data=json.dumps({'readings':[self.item()]}),
            content_type='application/json').status_code,401)
        self.assertEqual(CameraEnvironmentReading.objects.count(),0)

    def test_conflicting_event_id_rolls_back_whole_batch(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.send([self.item()]).status_code,200)
        r=self.send([self.item(temperature='7.1')])
        self.assertEqual(r.status_code,409)
        self.assertEqual(IoTReceipt.objects.count(),1)

    def test_sensor_wrong_gateway_or_facility(self):
        sensor=IoTDevice(gateway=self.ga,camera=self.cb,code='wrong',
            name='bad sensor',address=27)
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):sensor.full_clean()
        g=IoTGateway(organization=self.o,facility=self.fb,name='wrong',
            created_by=self.admin,secret_hash='test')
        with self.assertRaises(ValidationError):g.full_clean()

    def test_invalid_measurements_never_saved(self):
        old=(timezone.now()-timedelta(days=31)).isoformat()
        for item in [self.item(measured_at=old),
                     self.item(measured_at='2026-10-12T00:00:00'),
                     self.item(temperature='NaN'),
                     self.item(humidity='101')]:
            self.assertEqual(self.send([item]).status_code,400)
        self.assertFalse(IoTReceipt.objects.exists())

    def test_tenant_panel_and_gateway_creation(self):
        self.client.force_login(self.admin)
        page=self.client.get(reverse('iot_hub'))
        self.assertEqual(page.status_code,200)
        self.assertContains(page,'Gateway 1')
        self.assertNotContains(page,'Gateway B')
        self.assertEqual(self.client.post(reverse('iot_hub'),data={
            'action':'create_gateway','gateway-organization':str(self.b.pk),
            'gateway-facility':str(self.fb.pk),'gateway-name':'Intruder',
            'gateway-transport':'rs485','gateway-offline_minutes':'15'}).status_code,200)
        self.assertFalse(IoTGateway.objects.filter(name='Intruder').exists())
        self.client.force_login(self.admin_b)
        self.assertNotContains(self.client.get(reverse('iot_hub')),'Gateway 1')

    def test_disabled_gateway_rejects_new_measurements(self):
        self.ga.is_active=False
        self.ga.save()
        self.assertEqual(self.send([self.item()]).status_code,401)


    def test_sensor_offline_creates_and_recovers_one_incident(self):
        from warehouse.models import CameraEnvironmentAlert
        from warehouse.monitor_alerts import reconcile_camera
        sensor=self.sensors[0]
        sensor.last_seen_at=timezone.now()-timedelta(minutes=25)
        sensor.save(update_fields=['last_seen_at'])
        opened=reconcile_camera(self.cameras[0].pk)
        self.assertEqual([a.kind for a in opened],['sensor_offline'])
        self.assertEqual(reconcile_camera(self.cameras[0].pk),[])
        self.assertEqual(CameraEnvironmentAlert.objects.filter(
            camera=self.cameras[0],kind='sensor_offline').count(),1)
        sensor.last_seen_at=timezone.now()
        sensor.save(update_fields=['last_seen_at'])
        reconcile_camera(self.cameras[0].pk)
        self.assertFalse(CameraEnvironmentAlert.objects.filter(
            camera=self.cameras[0],kind='sensor_offline',
            resolved_at__isnull=True).exists())

    def test_offline_backlog_does_not_falsely_mark_sensor_online(self):
        old=(timezone.now()-timedelta(days=2)).isoformat()
        with self.captureOnCommitCallbacks(execute=True):
            result=self.send([self.item(measured_at=old,event_id='old-reading')])
        self.assertEqual(result.status_code,200,result.content)
        self.sensors[0].refresh_from_db()
        self.ga.refresh_from_db()
        self.assertFalse(self.sensors[0].online())
        self.assertTrue(self.ga.online())
        with self.captureOnCommitCallbacks(execute=True):
            result=self.send([self.item(event_id='new-reading')])
        self.assertEqual(result.status_code,200,result.content)
        self.sensors[0].refresh_from_db()
        self.assertTrue(self.sensors[0].online())
        stored=self.sensors[0].last_seen_at
        with self.captureOnCommitCallbacks(execute=True):
            result=self.send([self.item(measured_at=old,event_id='another-old-reading')])
        self.assertEqual(result.status_code,200,result.content)
        self.sensors[0].refresh_from_db()
        self.assertEqual(self.sensors[0].last_seen_at,stored)

    def test_mixed_gateway_supports_wifi_mqtt_and_modbus_devices(self):
        self.ga.transport='mixed'
        self.ga.full_clean()
        self.ga.save(update_fields=['transport'])
        from django.core.exceptions import ValidationError
        wifi=IoTDevice(gateway=self.ga,camera=self.cameras[0],
            transport='http_json',code='wifi01',name='Wi-Fi sensor')
        wifi.full_clean()
        wifi.save()
        mqtt=IoTDevice(gateway=self.ga,camera=self.cameras[1],
            transport='mqtt',code='mqtt02',name='MQTT sensor')
        mqtt.full_clean()
        mqtt.save()
        self.assertEqual(IoTDevice.objects.filter(gateway=self.ga).count(),27)
        invalid=IoTDevice(gateway=self.ga,camera=self.cameras[2],
            transport='modbus_rtu',code='bad',name='Missing register')
        with self.assertRaises(ValidationError):
            invalid.full_clean()
        invalid_wifi=IoTDevice(gateway=self.ga,camera=self.cameras[2],
            transport='http_json',code='bad-wifi',address=51,name='Invalid HTTP address')
        with self.assertRaises(ValidationError):
            invalid_wifi.full_clean()

    def test_bulk_pair_25_cameras_as_13_plus_12_on_separate_gateways(self):
        self.client.force_login(self.admin)
        from django.contrib.auth.hashers import make_password
        for label, segment in [('BULK-A',self.cameras[:13]),('BULK-B',self.cameras[13:])]:
            gateway=IoTGateway.objects.create(organization=self.o,facility=self.f,
                name=label,created_by=self.admin,transport='rs485',
                secret_hash=make_password('long-test-secret-bulk-only'))
            response=self.client.post(reverse('iot_hub'),data={
                'action':'bulk_modbus','bulk-gateway':str(gateway.pk),
                'bulk-cameras':[str(camera.pk) for camera in segment],
                'bulk-address_start':'1'})
            self.assertEqual(response.status_code,302,response.content[:400])
            sensors=list(IoTDevice.objects.filter(gateway=gateway).order_by('address'))
            self.assertEqual(len(sensors),len(segment))
            self.assertEqual([x.address for x in sensors],list(range(1,len(segment)+1)))
        self.assertEqual(IoTDevice.objects.filter(gateway__name__startswith='BULK').count(),25)

    def test_gateway_config_export_is_secret_free_and_tenant_scoped(self):
        url=reverse('iot_edge_config',args=[self.ga.pk])
        self.assertEqual(self.client.get(url).status_code,302)
        self.client.force_login(self.admin_b)
        self.assertEqual(self.client.get(url).status_code,404)
        self.client.force_login(self.admin)
        response=self.client.get(url)
        self.assertEqual(response.status_code,200,response.content[:400])
        self.assertEqual(response['Cache-Control'],'no-store, private')
        self.assertIn('attachment;',response['Content-Disposition'])
        data=response.json()
        self.assertEqual(data['_gateway_id'],str(self.ga.pk))
        self.assertEqual(len(data['devices']),25)
        self.assertEqual([d['address'] for d in data['devices']],list(range(1,26)))
        self.assertTrue(all(d['temperature_register'] is None for d in data['devices']))
        self.assertTrue(all(d['humidity_register'] is None for d in data['devices']))
        self.assertTrue(all(d['transport']=='modbus_rtu' for d in data['devices']))
        self.assertNotIn(self.secret,response.content.decode('utf8'))
        self.assertNotIn(self.ga.secret_hash,response.content.decode('utf8'))
        self.assertFalse(data['_contains_secrets'])

    def test_config_export_rejects_other_tenant_and_readonly_director(self):
        from django.contrib.auth import get_user_model
        from core.models import Membership
        U=get_user_model()
        director=U.objects.create_user('iot_director',password='Unrelatedpass909090!',is_staff=True)
        Membership.objects.create(user=director,organization=self.o,role='director',
            all_cameras=True,all_facilities=True)
        self.client.force_login(director)
        self.assertEqual(self.client.get(reverse('iot_edge_config',args=[self.ga.pk])).status_code,404)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('iot_edge_config',args=[self.gb.pk])).status_code,404)

    def test_single_protocol_gateway_rejects_incompatible_sensor(self):
        from django.core.exceptions import ValidationError
        wifi=IoTDevice(gateway=self.ga,camera=self.cameras[0],
            transport='http_json',code='wifi-on-rs485',name='Wrong protocol')
        with self.assertRaises(ValidationError):
            wifi.full_clean()
        self.ga.transport='mixed'
        self.ga.full_clean()
        self.ga.save(update_fields=['transport'])
        wifi.full_clean()
        wifi.save()
        self.assertEqual(wifi.transport,'http_json')

    def test_admin_on_a_can_only_view_other_organization_gateway(self):
        Membership.objects.create(user=self.admin,organization=self.b,
            role='director',all_cameras=True,all_facilities=True)
        self.client.force_login(self.admin)
        page=self.client.get(reverse('iot_hub'))
        self.assertEqual(page.status_code,200)
        self.assertContains(page,'Gateway 1')
        self.assertContains(page,'Gateway B')
        self.assertContains(page,'Faqat ko‘rish')
        self.assertEqual(page.content.decode('utf8').count('Konfiguratsiyani yuklab olish'),1)
        attempt=self.client.post(reverse('iot_hub'),data={
            'action':'rotate','gateway_id':str(self.gb.pk)})
        self.assertEqual(attempt.status_code,403)

    def test_25_cam_limit_is_per_tenant_not_global(self):
        self.assertEqual(len(self.cameras),25)
        self.assertEqual(self.o.cameras.count(),25)
        self.assertEqual(self.b.cameras.count(),1)
