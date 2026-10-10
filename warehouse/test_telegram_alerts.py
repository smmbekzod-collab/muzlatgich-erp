"""Telegram notifications are isolated, deduplicated, queued and retryable.

All Bot API calls are stubbed: never send a network request in CI.
"""
from datetime import timedelta
from decimal import Decimal as D
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase,override_settings
from django.urls import reverse
from django.utils import timezone
from core.models import Organization,Facility,Camera,Membership
from warehouse.models import (CameraEnvironmentPolicy,CameraEnvironmentReading,
    CameraEnvironmentAlert,TelegramAlertDestination)
from warehouse.monitor_alerts import reconcile_camera,scan_all_cameras
from warehouse.telegram_sender import drain_alerts


@override_settings(STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},
                            'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class TelegramAlertsTests(TestCase):
    def setUp(self):
        U=get_user_model()
        self.owner=U.objects.create_superuser('tg_owner',password='StrongTestPassword!444')
        self.director=U.objects.create_user('tg_director',password='StrongTestPassword!444',is_staff=True)
        self.keeper=U.objects.create_user('tg_keeper',password='StrongTestPassword!444',is_staff=True)
        self.stranger=U.objects.create_user('tg_stranger',password='StrongTestPassword!444',is_staff=True)
        self.o=Organization.objects.create(name='Birinchi Ombor',code='telegram-one',camera_limit=4)
        self.other=Organization.objects.create(name='Ikkinchi Ombor',code='telegram-two',camera_limit=4)
        b=Facility.objects.create(organization=self.o,name='Asosiy',code='main')
        b2=Facility.objects.create(organization=self.other,name='Begona',code='main')
        self.cam=Camera.objects.create(organization=self.o,facility=b,number=1)
        self.cam_other=Camera.objects.create(organization=self.other,facility=b2,number=1)
        self.channel=TelegramAlertDestination.objects.create(
            organization=self.o,chat_id='-100123456',enabled=True,updated_by=self.owner)
        self.other_channel=TelegramAlertDestination.objects.create(
            organization=self.other,chat_id='-100654321',enabled=True,updated_by=self.owner)
        self.policy=CameraEnvironmentPolicy.objects.create(
            camera=self.cam,updated_by=self.owner,
            min_temperature=D('-1'),max_temperature=D('2'),min_humidity=D('70'),
            max_humidity=D('95'),check_interval_hours=12)
        self.policy_other=CameraEnvironmentPolicy.objects.create(
            camera=self.cam_other,updated_by=self.owner,
            max_temperature=D('2'),check_interval_hours=12)
        Membership.objects.create(user=self.director,organization=self.o,role='director',
                                  all_cameras=True,all_facilities=True,can_view_finance=True)
        Membership.objects.create(user=self.keeper,organization=self.o,role='keeper',
                                  all_cameras=True,all_facilities=True,can_monitor_environment=True)
        Membership.objects.create(user=self.stranger,organization=self.other,role='director',
                                  all_cameras=True,all_facilities=True,can_view_finance=True)

    def reading(self,temperature='4',humidity='88',camera=None):
        camera=camera or self.cam
        return CameraEnvironmentReading.objects.create(camera=camera,
            measured_at=timezone.now()-timedelta(minutes=2),
            temperature=D(temperature),humidity=D(humidity),recorded_by=self.keeper)

    def test_new_violation_is_one_open_incident_even_after_repeat(self):
        self.reading()
        created=reconcile_camera(self.cam.pk)
        self.assertEqual([x.kind for x in created],['temp_high'])
        alert=CameraEnvironmentAlert.objects.get(camera=self.cam,kind='temp_high')
        self.assertEqual(alert.delivery_status,'pending')
        self.reading('5')
        self.assertEqual(reconcile_camera(self.cam.pk),[])
        self.assertEqual(CameraEnvironmentAlert.objects.filter(camera=self.cam).count(),1)

    def test_recovery_then_new_violation_reopens_new_event(self):
        self.reading()
        reconcile_camera(self.cam.pk)
        self.reading('0')
        reconcile_camera(self.cam.pk)
        first=CameraEnvironmentAlert.objects.get(camera=self.cam)
        self.assertIsNotNone(first.resolved_at)
        self.reading('5')
        reconcile_camera(self.cam.pk)
        self.assertEqual(CameraEnvironmentAlert.objects.filter(camera=self.cam).count(),2)
        self.assertEqual(CameraEnvironmentAlert.objects.filter(camera=self.cam,
            resolved_at__isnull=True).count(),1)

    def test_missing_channel_creates_local_incident_not_fake_sent(self):
        self.channel.enabled=False
        self.channel.save()
        self.reading()
        reconcile_camera(self.cam.pk)
        event=CameraEnvironmentAlert.objects.get(camera=self.cam)
        self.assertEqual(event.delivery_status,'disabled')
        self.assertIsNone(event.sent_at)

    def test_stale_is_detected_by_periodic_scan_without_new_post(self):
        self.reading(temperature='1')
        CameraEnvironmentReading.objects.filter(camera=self.cam).update(
            measured_at=timezone.now()-timedelta(hours=17))
        checked,created=scan_all_cameras()
        self.assertEqual(checked,2)
        self.assertGreaterEqual(created,1)
        self.assertTrue(CameraEnvironmentAlert.objects.filter(camera=self.cam,kind='stale',
            resolved_at__isnull=True).exists())

    @patch.dict('os.environ',{},clear=True)
    def test_no_bot_token_skips_delivery(self):
        self.reading()
        reconcile_camera(self.cam.pk)
        result=drain_alerts()
        self.assertTrue(result['skipped'])
        alert=CameraEnvironmentAlert.objects.get(camera=self.cam)
        self.assertEqual(alert.delivery_status,'pending')
        self.assertEqual(alert.attempts,0)

    @patch.dict('os.environ',{'TELEGRAM_BOT_TOKEN':'123:testing'},clear=False)
    @patch('warehouse.telegram_sender.send_message')
    def test_sends_exactly_once_to_correct_chat(self,send):
        self.reading()
        reconcile_camera(self.cam.pk)
        first=drain_alerts()
        self.assertEqual(first['sent'],1)
        self.assertEqual(first['failed'],0)
        self.assertEqual(send.call_count,1)
        self.assertEqual(send.call_args.args[1],'-100123456')
        self.assertIn('Birinchi Ombor',send.call_args.args[2])
        self.assertNotIn('Ikkinchi Ombor',send.call_args.args[2])
        self.assertEqual(drain_alerts()['sent'],0)
        self.assertEqual(send.call_count,1)
        alert=CameraEnvironmentAlert.objects.get(camera=self.cam)
        self.assertEqual(alert.delivery_status,'sent')
        self.assertEqual(alert.attempts,1)
        self.assertIsNotNone(alert.sent_at)

    @patch.dict('os.environ',{'TELEGRAM_BOT_TOKEN':'123:testing'},clear=False)
    @patch('warehouse.telegram_sender.send_message',side_effect=RuntimeError('Telegram HTTP 403'))
    def test_delivery_error_keeps_retryable_log(self,send):
        self.reading()
        reconcile_camera(self.cam.pk)
        r=drain_alerts()
        self.assertEqual(r['failed'],1)
        event=CameraEnvironmentAlert.objects.get(camera=self.cam)
        self.assertEqual(event.delivery_status,'failed')
        self.assertEqual(event.attempts,1)
        self.assertEqual(event.last_error,'Telegram HTTP 403')
        self.assertIsNotNone(event.next_attempt_at)
        self.assertEqual(drain_alerts()['failed'],0)

    def test_cross_tenant_cannot_read_director_dashboard_data(self):
        self.reading()
        reconcile_camera(self.cam.pk)
        self.client.force_login(self.stranger)
        res=self.client.get(reverse('director_monitor'))
        self.assertEqual(res.status_code,200)
        self.assertNotContains(res,'Birinchi Ombor')
        self.assertNotContains(res,'temp_high')
        self.assertContains(res,'Ikkinchi Ombor')

    def test_keeper_is_not_finance_admin(self):
        self.client.force_login(self.keeper)
        result=self.client.get(reverse('director_monitor'))
        self.assertEqual(result.status_code,200)
        self.assertNotContains(result,'Birinchi Ombor')
        self.assertEqual(result.context['total_visible_cameras'],0)

    def test_superadmin_only_chat_setup(self):
        self.client.force_login(self.stranger)
        url=reverse('telegram_destinations')
        self.assertEqual(self.client.get(url).status_code,403)
        self.assertEqual(self.client.post(url,{}).status_code,403)
        self.client.force_login(self.owner)
        self.assertContains(self.client.get(url),'Telegram ogohlantirishlari')
        res=self.client.post(url,{'organization':self.o.pk,'chat_id':'-100987123','enabled':'on'})
        self.assertEqual(res.status_code,302)
        self.channel.refresh_from_db()
        self.assertEqual(self.channel.chat_id,'-100987123')
        self.assertTrue(self.channel.enabled)
        bad=self.client.post(url,{'organization':self.o.pk,'chat_id':'invalid','enabled':'on'})
        self.assertEqual(bad.status_code,200)
        self.channel.refresh_from_db()
        self.assertEqual(self.channel.chat_id,'-100987123')

    def test_new_manual_reading_creates_incident_via_form(self):
        self.client.force_login(self.keeper)
        data={'action':'reading',
           'reading-measured_at':timezone.localtime(
               timezone.now()-timedelta(minutes=2)).strftime('%Y-%m-%dT%H:%M'),
           'reading-temperature':'4','reading-humidity':'86','reading-note':'test'}
        response=self.client.post(reverse('monitor_camera',args=[self.cam.pk]),data)
        self.assertEqual(response.status_code,302)
        self.assertTrue(CameraEnvironmentAlert.objects.filter(camera=self.cam,
            kind='temp_high',resolved_at__isnull=True).exists())

    def test_management_command_without_token_does_not_contact_telegram(self):
        with patch.dict('os.environ',{},clear=True):
            with patch('warehouse.telegram_sender.send_message') as send:
                call_command('process_monitor_alerts','--limit=2','--send-limit=3',verbosity=0)
                send.assert_not_called()
