from datetime import timedelta
from decimal import Decimal as D
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone
from core.models import Organization, Facility, Camera, Membership
from warehouse.models import CameraEnvironmentPolicy, CameraEnvironmentReading
from warehouse.environment_logic import assess_camera

@override_settings(STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class MonitoringTests(TestCase):
    def setUp(self):
        U=get_user_model()
        self.admin=U.objects.create_superuser('monitor_super',password='StrongPass!98213')
        self.keeper=U.objects.create_user('monitor_keeper',password='StrongPass!98213',is_staff=True)
        self.director=U.objects.create_user('monitor_director',password='StrongPass!98213',is_staff=True)
        self.outsider=U.objects.create_user('monitor_outsider',password='StrongPass!98213',is_staff=True)
        self.o=Organization.objects.create(name='Fargona',code='env-a',camera_limit=3)
        self.o2=Organization.objects.create(name='Toshkent',code='env-b',camera_limit=3)
        b=Facility.objects.create(organization=self.o,name='Asosiy',code='main')
        b2=Facility.objects.create(organization=self.o2,name='Asosiy',code='main')
        self.c=Camera.objects.create(organization=self.o,facility=b,number=1)
        self.c2=Camera.objects.create(organization=self.o2,facility=b2,number=1)
        Membership.objects.create(user=self.keeper,organization=self.o,all_cameras=True,
                                  can_monitor_environment=True,can_receive=True)
        Membership.objects.create(user=self.director,organization=self.o,all_cameras=True,
                                  can_view_finance=True)
        Membership.objects.create(user=self.outsider,organization=self.o2,all_cameras=True,
                                  can_monitor_environment=True,can_set_tariffs=True)
        self.url=reverse('monitor_camera',args=[self.c.pk])
        self.overview=reverse('monitor_overview')

    def data(self,temperature='1.5',humidity='88',when=None):
        when=when or timezone.now()-timedelta(minutes=3)
        return {'action':'reading','reading-measured_at':timezone.localtime(when).strftime('%Y-%m-%dT%H:%M'),
            'reading-temperature':temperature,'reading-humidity':humidity,'reading-note':'Qo‘l bilan'}

    def limits(self,**kwargs):
        data={'action':'policy','policy-min_temperature':'-1','policy-max_temperature':'2',
              'policy-min_humidity':'85','policy-max_humidity':'95',
              'policy-check_interval_hours':'12','policy-max_storage_days':'30'}
        data.update(kwargs)
        return data

    def test_grape_carrot_potato_profiles_are_advisory(self):
        from warehouse.crop_profiles import REFERENCES, classify_product, camera_crop_status
        self.assertEqual([ref.code for ref in REFERENCES],
                         ['grape','carrot','potato','potato_processing','onion_dry'])
        self.assertEqual(classify_product('Qora uzum'), 'grape')
        self.assertEqual(classify_product('Sabzi'), 'carrot')
        self.assertEqual(classify_product('Kartoshka'), 'potato')
        self.assertEqual(classify_product('Quruq piyoz'), 'onion_dry')
        self.assertIsNone(classify_product("ko'k piyoz"))
        self.assertIsNone(classify_product('ko‘k piyoz'))
        self.assertIsNone(classify_product('yashil piyoz'))
        self.assertIsNone(classify_product('sabzavot'))
        self.assertEqual(camera_crop_status(['uzum','kartoshka'])['state'],'mixed')
        self.assertEqual(camera_crop_status(['sabzi','kartoshka'])['state'],'mixed')
        self.assertEqual(camera_crop_status(['uzum','sabzi'])['state'],'mixed')
        self.assertEqual(camera_crop_status(['uzum','noma’lum'])['state'],'unknown')
        self.assertEqual(camera_crop_status(['sabzi'])['kind'],'carrot')
        self.client.force_login(self.admin)
        response=self.client.get(self.url)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.context['crop_status']['state'],'empty')
        self.assertEqual(len(response.context['crop_references']),5)
        self.assertFalse(CameraEnvironmentPolicy.objects.filter(camera=self.c).exists())

    def test_blank_product_does_not_silently_choose_first_preset(self):
        self.client.force_login(self.admin)
        response=self.client.post(self.url,{
            'action':'preset','preset-profile_code':''})
        self.assertEqual(response.status_code,200)
        self.assertFalse(CameraEnvironmentPolicy.objects.filter(camera=self.c).exists())

    def test_selecting_crop_changes_camera_monitoring_limits_without_manual_retyping(self):
        from warehouse.models import CameraEnvironmentProfileChange
        self.client.force_login(self.admin)
        for code,expected in [
            ('grape',('-1.00','0.00','90.00','95.00')),
            ('carrot',('0.00','1.00','98.00','100.00')),
            ('potato',('4.00','8.00','90.00','96.00')),
            ('potato_processing',('7.00','10.00','90.00','96.00')),
            ('onion_dry',('0.00','1.00','65.00','70.00')),
        ]:
            response=self.client.post(self.url,{
                'action':'preset','preset-profile_code':code})
            self.assertEqual(response.status_code,302,response.content[:300])
            p=CameraEnvironmentPolicy.objects.get(camera=self.c)
            self.assertEqual(p.profile_code,code)
            actual=tuple(str(getattr(p,key)) for key in (
                'min_temperature','max_temperature','min_humidity','max_humidity'))
            self.assertEqual(actual,expected)
            self.assertEqual(p.check_interval_hours,12)
        self.assertEqual(CameraEnvironmentProfileChange.objects.filter(camera=self.c).count(),5)
        self.assertEqual(CameraEnvironmentProfileChange.objects.filter(
            camera=self.c).first().previous_profile,'potato_processing')
        self.assertEqual(CameraEnvironmentProfileChange.objects.filter(
            camera=self.c).first().current_profile,'onion_dry')
        self.assertContains(self.client.get(self.url),'Piyoz')

    def test_manual_adjustment_exits_automatic_profile_without_loss_of_other_options(self):
        from warehouse.models import CameraEnvironmentProfileChange
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(self.url,{
            'action':'preset','preset-profile_code':'onion_dry'}).status_code,302)
        before=CameraEnvironmentPolicy.objects.get(camera=self.c)
        before.max_storage_days=37
        before.check_interval_hours=4
        before.save()
        result=self.client.post(self.url,self.limits(**{
            'policy-min_temperature':'0','policy-max_temperature':'2',
            'policy-min_humidity':'65','policy-max_humidity':'75',
            'policy-check_interval_hours':'4','policy-max_storage_days':'37'}))
        self.assertEqual(result.status_code,302,result.content[:300])
        p=CameraEnvironmentPolicy.objects.get(camera=self.c)
        self.assertEqual(p.profile_code,'')
        self.assertEqual(str(p.max_humidity),'75.00')
        self.assertEqual(p.max_storage_days,37)
        self.assertEqual(p.check_interval_hours,4)
        self.assertEqual(CameraEnvironmentProfileChange.objects.filter(camera=self.c).count(),2)
        self.assertEqual(CameraEnvironmentProfileChange.objects.filter(
            camera=self.c).first().previous_profile,'onion_dry')

    def test_camera_with_other_open_product_blocks_automatic_switch(self):
        import uuid
        from warehouse.models import Customer,Lot
        from warehouse.models import CameraEnvironmentProfileChange
        customer=Customer.objects.create(organization=self.o,name='Sinov mijoz')
        today=timezone.localdate()
        lot=Lot.objects.create(
            create_key=uuid.uuid4(), organization=self.o,camera=self.c,customer=customer,
            product='Sabzi',box_type='yashik',received_on=today,last_stock_date=today,
            initial_boxes=5,initial_gross=D('100'),initial_tare=D('5'),
            boxes=5,gross=D('100'),tare=D('5'),tariff_name='sinov',
            service='storage',basis='net',rate=D('0'),storage_mode='prorata',
            created_by=self.admin)
        self.client.force_login(self.admin)
        wrong=self.client.post(self.url,{
            'action':'preset','preset-profile_code':'onion_dry'})
        self.assertEqual(wrong.status_code,200)
        self.assertContains(wrong,'boshqa yoki aniqlanmagan mahsulot')
        self.assertFalse(CameraEnvironmentPolicy.objects.filter(camera=self.c).exists())
        okay=self.client.post(self.url,{
            'action':'preset','preset-profile_code':'carrot'})
        self.assertEqual(okay.status_code,302,okay.content[:300])
        self.assertEqual(CameraEnvironmentPolicy.objects.get(
            camera=self.c).profile_code,'carrot')
        lot.closed_on=today
        lot.save()
        self.assertEqual(self.client.post(self.url,{
            'action':'preset','preset-profile_code':'onion_dry'}).status_code,302)
        self.assertEqual(CameraEnvironmentPolicy.objects.get(
            camera=self.c).profile_code,'onion_dry')
        self.assertEqual(CameraEnvironmentProfileChange.objects.filter(
            camera=self.c).count(),2)

    def test_operator_cannot_select_or_change_product_preset(self):
        self.client.force_login(self.keeper)
        response=self.client.post(self.url,{
            'action':'preset','preset-profile_code':'onion_dry'})
        self.assertEqual(response.status_code,403)
        self.assertFalse(CameraEnvironmentPolicy.objects.exists())
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.post(self.url,{
            'action':'preset','preset-profile_code':'carrot'}).status_code,404)

    def test_login_and_cross_tenant_isolation(self):
        self.assertEqual(self.client.get(self.url).status_code,302)
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(self.url).status_code,404)
        self.assertEqual(self.client.post(self.url,self.data()).status_code,404)
        page=self.client.get(self.overview)
        self.assertNotContains(page,'Fargona')
        self.assertContains(page,'Toshkent')

    def test_keeper_can_record_but_not_set_limits(self):
        self.client.force_login(self.keeper)
        self.assertEqual(self.client.post(self.url,self.data()).status_code,302)
        self.assertEqual(CameraEnvironmentReading.objects.get().source,'manual')
        self.assertEqual(self.client.post(self.url,self.limits()).status_code,403)
        self.assertFalse(CameraEnvironmentPolicy.objects.exists())
        self.assertContains(self.client.get(self.url),'Qo‘l bilan')

    def test_director_is_readonly(self):
        self.client.force_login(self.director)
        self.assertEqual(self.client.get(self.url).status_code,200)
        self.assertEqual(self.client.post(self.url,self.data()).status_code,403)
        self.assertEqual(self.client.post(self.url,self.limits()).status_code,403)

    def test_admin_sets_limits_and_reports_high_temperature(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(self.url,self.limits()).status_code,302)
        self.assertEqual(CameraEnvironmentPolicy.objects.get(camera=self.c).max_temperature,D('2'))
        self.client.force_login(self.keeper)
        self.assertEqual(self.client.post(self.url,self.data(temperature='4')).status_code,302)
        self.assertContains(self.client.get(self.url),'Harorat belgilangan yuqori chegaradan oshgan')
        self.assertContains(self.client.get(self.overview),'E’tibor talab etiladi')

    def test_missing_limits_not_treated_as_safe(self):
        self.client.force_login(self.keeper)
        self.assertEqual(self.client.post(self.url,self.data()).status_code,302)
        self.assertContains(self.client.get(self.url),'Me’yor sozlanmagan')
        self.assertNotContains(self.client.get(self.url),'Kiritilgan chegaralarda')

    def test_invalid_limits_and_readings_rejected(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(self.url,self.limits(**{'policy-min_temperature':'8','policy-max_temperature':'2'})).status_code,200)
        self.assertFalse(CameraEnvironmentPolicy.objects.exists())
        self.client.force_login(self.keeper)
        for temp,humid in [('81','85'),('-81','85'),('1','101'),('1','-1')]:
            self.assertEqual(self.client.post(self.url,self.data(temp,humid)).status_code,200)
        self.assertFalse(CameraEnvironmentReading.objects.exists())

    def test_future_and_old_time_invalid(self):
        self.client.force_login(self.keeper)
        for when in [timezone.now()+timedelta(hours=1),timezone.now()-timedelta(days=91)]:
            self.assertEqual(self.client.post(self.url,self.data(when=when)).status_code,200)
        self.assertFalse(CameraEnvironmentReading.objects.exists())

    def test_history_immutable(self):
        obj=CameraEnvironmentReading.objects.create(camera=self.c,
            measured_at=timezone.now(),temperature=D('1'),humidity=D('82'),
            recorded_by=self.keeper)
        obj.temperature=D('3')
        with self.assertRaises(ValidationError):obj.save()
        obj.refresh_from_db()
        self.assertEqual(obj.temperature,D('1'))

    def test_stale_reading_and_age_warning(self):
        p=CameraEnvironmentPolicy.objects.create(camera=self.c,updated_by=self.admin,
            min_temperature=D('-1'),max_temperature=D('2'),
            check_interval_hours=12,max_storage_days=10)
        when=timezone.now()
        r=CameraEnvironmentReading.objects.create(camera=self.c,
            measured_at=when-timedelta(hours=1),temperature=D('2'),humidity=D('88'),recorded_by=self.keeper)
        self.assertEqual(assess_camera(self.c,p,r,None,when)['state'],'good')
        late=assess_camera(self.c,p,r,None,when+timedelta(hours=13))
        self.assertEqual(late['state'],'alert')
        self.assertTrue(any('eskirgan' in s for s in late['issues']))
        old=(timezone.localtime(when)-timedelta(days=15)).date()
        age=assess_camera(self.c,p,None,old,when)
        self.assertTrue(age['days_warning'])
        self.assertEqual(age['storage_days'],16)


    def test_monitor_csv_exports_only_authorized_camera_and_escapes_cells(self):
        CameraEnvironmentReading.objects.create(camera=self.c,
            measured_at=timezone.now()-timedelta(hours=1),
            temperature=D('-1'),humidity=D('88'),note='=SUM(A1:A2)',
            recorded_by=self.keeper)
        CameraEnvironmentReading.objects.create(camera=self.c2,
            measured_at=timezone.now()-timedelta(hours=1),
            temperature=D('3'),humidity=D('50'),note='SECRET OTHER TENANT',
            recorded_by=self.outsider)
        self.client.force_login(self.keeper)
        path=reverse('monitor_csv',args=[self.c.pk])
        result=self.client.get(path)
        self.assertEqual(result.status_code,200)
        self.assertIn('text/csv',result['Content-Type'])
        text=result.content.decode('utf-8-sig')
        self.assertIn('=SUM(A1:A2)',text)
        self.assertIn("'=SUM",text)
        self.assertIn('Fargona',text)
        self.assertNotIn('SECRET OTHER TENANT',text)
        forbidden=self.client.get(reverse('monitor_csv',args=[self.c2.pk]))
        self.assertEqual(forbidden.status_code,404)

    def test_monitor_csv_excludes_old_readings(self):
        CameraEnvironmentReading.objects.create(camera=self.c,
            measured_at=timezone.now()-timedelta(days=32),
            temperature=D('1'),humidity=D('90'),note='OLD READING',
            recorded_by=self.keeper)
        self.client.force_login(self.admin)
        csv_text=self.client.get(reverse('monitor_csv',args=[self.c.pk])).content.decode('utf-8')
        self.assertNotIn('OLD READING',csv_text)

    def test_csrf_and_unknown_action(self):
        browser=Client(enforce_csrf_checks=True)
        browser.force_login(self.keeper)
        self.assertEqual(browser.post(self.url,self.data()).status_code,403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(self.url,{'action':'mystery'}).status_code,403)
