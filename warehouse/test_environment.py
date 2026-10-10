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

    def test_csrf_and_unknown_action(self):
        browser=Client(enforce_csrf_checks=True)
        browser.force_login(self.keeper)
        self.assertEqual(browser.post(self.url,self.data()).status_code,403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(self.url,{'action':'mystery'}).status_code,403)
