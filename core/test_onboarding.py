"""Regression coverage for mobile Super Admin onboarding and tenant isolation."""
from django.contrib.auth import get_user_model
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from core.models import Organization, Facility, Camera


@override_settings(STORAGES={
    'default': {'BACKEND':'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class PlatformOnboardingTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            'platform_owner', password='OnlyForTest!902188')
        self.staff = get_user_model().objects.create_user(
            'warehouse_employee', password='OnlyForTest!902188', is_staff=True)
        self.url = reverse('platform_dashboard')

    def organization(self, name='Agro Test MCHJ', code='agro-test', limit=2):
        return Organization.objects.create(name=name, code=code, camera_limit=limit)

    def branch(self, org, name='Oltiariq', code='oltiariq'):
        return Facility.objects.create(
            organization=org, name=name, code=code,
            region='Farg‘ona', district='Oltiariq')

    def post_org(self, name='Agro Test MCHJ', code='agro-test', limit='2'):
        return self.client.post(self.url, {
            'action':'organization',
            'org-name':name, 'org-code':code, 'org-camera_limit':limit,
        })

    def post_branch(self, org_id, name='Asosiy ombor', code='main-branch'):
        return self.client.post(self.url, {
            'action':'facility',
            'branch-organization':org_id, 'branch-name':name,
            'branch-code':code, 'branch-region':'Farg‘ona',
            'branch-district':'Oltiariq', 'branch-address':'TEST manzil',
        })

    def post_cam(self, facility_id, number='1', capacity='23000'):
        return self.client.post(self.url, {
            'action':'camera', 'cam-facility':facility_id, 'cam-number':number,
            'cam-name':'Meva kamerasi', 'cam-capacity_kg':capacity,
            'organization':'999999',  # Client must never decide Camera.organization.
        })

    def test_unauthenticated_user_is_redirected_to_login(self):
        res=self.client.get(self.url)
        self.assertEqual(res.status_code,302)
        self.assertIn('/admin/login/',res['Location'])

    def test_regular_staff_gets_403_on_get_and_post(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(self.url).status_code,403)
        self.assertEqual(self.post_org().status_code,403)
        self.assertEqual(Organization.objects.count(),0)

    def test_no_dummy_records_created_on_get(self):
        self.client.force_login(self.admin)
        res=self.client.get(self.url)
        self.assertEqual(res.status_code,200)
        self.assertContains(res,'Tashkilot qo‘shish')
        self.assertContains(res,'Kamera qo‘shish')
        self.assertEqual(Organization.objects.count(),0)
        self.assertEqual(Facility.objects.count(),0)
        self.assertEqual(Camera.objects.count(),0)

    def test_three_steps_are_functional(self):
        self.client.force_login(self.admin)
        r=self.post_org()
        self.assertEqual(r.status_code,302)
        org=Organization.objects.get(code='agro-test')
        self.assertEqual(org.camera_limit,2)
        r=self.post_branch(org.pk)
        self.assertEqual(r.status_code,302)
        branch=Facility.objects.get(organization=org,code='main-branch')
        self.assertEqual(branch.address,'TEST manzil')
        r=self.post_cam(branch.pk)
        self.assertEqual(r.status_code,302)
        cam=Camera.objects.get(facility=branch,number=1)
        self.assertEqual(cam.organization_id,org.pk)
        self.assertEqual(str(cam.capacity_kg),'23000.00')
        self.assertEqual(Camera.objects.count(),1)
        dashboard=self.client.get(reverse('dashboard'))
        self.assertContains(dashboard,'Asosiy ombor')

    def test_duplicate_company_code_shows_error_not_exception(self):
        self.client.force_login(self.admin)
        self.organization()
        r=self.post_org(code='agro-test')
        self.assertEqual(r.status_code,200)
        self.assertContains(r,'errorlist')
        self.assertEqual(Organization.objects.count(),1)

    def test_duplicate_branch_code_in_same_org_rejected(self):
        self.client.force_login(self.admin)
        org=self.organization()
        self.branch(org,code='main-branch')
        r=self.post_branch(org.pk,code='main-branch')
        self.assertEqual(r.status_code,200)
        self.assertContains(r,'errorlist')
        self.assertEqual(Facility.objects.count(),1)

    def test_same_camera_number_allowed_across_branches(self):
        self.client.force_login(self.admin)
        org=self.organization()
        one=self.branch(org)
        two=self.branch(org, name='Quva', code='quva')
        self.assertEqual(self.post_cam(one.pk,number='1').status_code,302)
        self.assertEqual(self.post_cam(two.pk,number='1').status_code,302)
        self.assertEqual(Camera.objects.count(),2)

    def test_camera_duplicate_and_org_quota_rejected(self):
        self.client.force_login(self.admin)
        org=self.organization(limit=1)
        branch=self.branch(org)
        self.assertEqual(self.post_cam(branch.pk,number='1').status_code,302)
        same=self.post_cam(branch.pk,number='1')
        self.assertEqual(same.status_code,200)
        self.assertContains(same,'errorlist')
        over=self.post_cam(branch.pk,number='2')
        self.assertEqual(over.status_code,200)
        self.assertContains(over,'limitiga yetgan')
        self.assertEqual(Camera.objects.count(),1)

    def test_camera_requires_valid_facility_and_positive_capacity(self):
        self.client.force_login(self.admin)
        org=self.organization()
        branch=self.branch(org)
        invalid=self.post_cam(branch.pk,capacity='0')
        self.assertEqual(invalid.status_code,200)
        self.assertEqual(Camera.objects.count(),0)
        missing=self.post_cam('999999')
        self.assertEqual(missing.status_code,200)
        self.assertEqual(Camera.objects.count(),0)

    def test_deactivated_branch_cannot_be_used(self):
        self.client.force_login(self.admin)
        org=self.organization()
        branch=self.branch(org)
        branch.is_active=False
        branch.save()
        invalid=self.post_cam(branch.pk)
        self.assertEqual(invalid.status_code,200)
        self.assertEqual(Camera.objects.count(),0)

    def test_valid_organization_is_taken_from_branch_not_post_data(self):
        self.client.force_login(self.admin)
        a=self.organization(code='a')
        b=self.organization(name='Other MCHJ',code='b')
        branch=self.branch(a)
        r=self.post_cam(branch.pk)
        self.assertEqual(r.status_code,302)
        self.assertEqual(Camera.objects.get().organization_id,a.pk)
        self.assertNotEqual(Camera.objects.get().organization_id,b.pk)

    def test_search_does_not_leak_other_org_data_to_staff(self):
        self.client.force_login(self.admin)
        self.organization(name='Farg‘ona Meva',code='meva')
        self.organization(name='Toshkent Fruit',code='fruit')
        r=self.client.get(self.url,{'q':'Fruit'})
        self.assertContains(r,'Toshkent Fruit')
        self.assertEqual([item.code for item in r.context['organizations']], ['fruit'])
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(self.url,{'q':'Fruit'}).status_code,403)

    def test_csrf_token_enforced_when_browser_posts(self):
        self.organization()
        browser=Client(enforce_csrf_checks=True)
        browser.force_login(self.admin)
        bad=browser.post(self.url,{
            'action':'organization', 'org-name':'Injected Test', 'org-code':'injected',
            'org-camera_limit':'2'})
        self.assertEqual(bad.status_code,403)
        self.assertFalse(Organization.objects.filter(code='injected').exists())

    def test_superadmin_shortcut_visible_only_to_superadmin(self):
        self.client.force_login(self.admin)
        r=self.client.get(reverse('dashboard'))
        self.assertContains(r,reverse('platform_dashboard'))
        self.client.force_login(self.staff)
        r=self.client.get(reverse('dashboard'))
        self.assertNotContains(r,'Tashkilot va kameralar')
