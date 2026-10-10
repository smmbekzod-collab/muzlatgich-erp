"""Regression tests: one-step staff login, tenant scope, permissions and revocation."""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from core import access
from core.models import Camera, Facility, Membership, Organization


@override_settings(STORAGES={
    'default': {'BACKEND':'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class StaffOnboardingTests(TestCase):
    def setUp(self):
        self.User=get_user_model()
        self.owner=self.User.objects.create_superuser('platform_superadmin',password='StrongForTests!312')
        self.nonadmin=self.User.objects.create_user('simple_keeper',password='StrongForTests!312',is_staff=True)
        self.org=Organization.objects.create(name='Agro Test',code='agro-test',camera_limit=5)
        self.other=Organization.objects.create(name='Farmer Test',code='farmer-test',camera_limit=5)
        self.f1=Facility.objects.create(organization=self.org,name='Oltiariq',code='oltiariq')
        self.f2=Facility.objects.create(organization=self.org,name='Quva',code='quva')
        self.foreign=Facility.objects.create(organization=self.other,name='Other',code='other')
        self.c1=Camera.objects.create(organization=self.org,facility=self.f1,number=1)
        self.c2=Camera.objects.create(organization=self.org,facility=self.f2,number=2)
        self.c3=Camera.objects.create(organization=self.other,facility=self.foreign,number=1)
        self.url=reverse('staff_dashboard')

    def payload(self, username='newstaff', role='keeper', organization=None, facility=None):
        return {
            'action':'create','staff-organization':str(organization or self.org.pk),
            'staff-username':username,'staff-first_name':'Sinov',
            'staff-last_name':'Xodim','staff-role':role,
            'staff-facility':str(facility) if facility is not None else '',
            'staff-password1':'VeryStrong!12x-Password','staff-password2':'VeryStrong!12x-Password',
        }

    def test_login_required_and_staff_forbidden(self):
        self.assertEqual(self.client.get(self.url).status_code,302)
        self.client.force_login(self.nonadmin)
        self.assertEqual(self.client.get(self.url).status_code,403)
        self.assertEqual(self.client.post(self.url,self.payload()).status_code,403)
        self.assertFalse(self.User.objects.filter(username='newstaff').exists())

    def test_empty_get_does_not_create_employee(self):
        self.client.force_login(self.owner)
        res=self.client.get(self.url)
        self.assertEqual(res.status_code,200)
        self.assertContains(res,'Xodimlar va huquqlar')
        self.assertFalse(self.User.objects.filter(username='newstaff').exists())

    def test_create_keeper_for_one_branch(self):
        self.client.force_login(self.owner)
        response=self.client.post(self.url,self.payload(facility=self.f1.pk))
        self.assertEqual(response.status_code,302,response.content[:500])
        employee=self.User.objects.get(username='newstaff')
        self.assertTrue(employee.is_staff)
        self.assertFalse(employee.is_superuser)
        self.assertTrue(employee.check_password('VeryStrong!12x-Password'))
        grant=Membership.objects.get(user=employee,organization=self.org)
        self.assertEqual(grant.role,'keeper')
        self.assertFalse(grant.all_facilities)
        self.assertTrue(grant.all_cameras)
        self.assertEqual(list(grant.facilities.values_list('pk',flat=True)),[self.f1.pk])
        self.assertTrue(grant.can_receive)
        self.assertTrue(grant.can_dispatch)
        self.assertTrue(grant.can_transfer)
        self.assertFalse(grant.can_view_finance)
        self.assertFalse(grant.can_take_payment)
        self.assertFalse(grant.can_set_tariffs)
        self.assertFalse(grant.can_dispatch_on_debt)
        self.assertEqual(list(access.cameras(employee).values_list('pk',flat=True)),[self.c1.pk])
        self.assertFalse(access.cameras(employee).filter(pk=self.c2.pk).exists())
        self.assertFalse(access.cameras(employee).filter(pk=self.c3.pk).exists())
        self.client.force_login(employee)
        self.assertEqual(self.client.get(reverse('dashboard')).status_code,200)
        self.assertEqual(self.client.get(self.url).status_code,403)

    def test_all_branches_but_never_other_organization(self):
        self.client.force_login(self.owner)
        response=self.client.post(self.url,self.payload(username='director1',role='director'))
        self.assertEqual(response.status_code,302)
        employee=self.User.objects.get(username='director1')
        self.assertEqual(set(access.cameras(employee).values_list('pk',flat=True)),{self.c1.pk,self.c2.pk})
        grant=Membership.objects.get(user=employee,organization=self.org)
        self.assertTrue(grant.all_facilities)
        self.assertTrue(grant.can_view_finance)
        self.assertFalse(grant.can_receive)
        self.assertFalse(grant.can_dispatch)

    def test_role_templates_are_distinct(self):
        for role,expected in (
            ('admin',('can_set_tariffs','can_manage_expenses','can_receive')),
            ('accountant',('can_view_finance','can_take_payment','can_manage_expenses')),
            ('keeper',('can_receive','can_dispatch','can_transfer')),
            ('director',('can_view_finance',)),
        ):
            with self.subTest(role=role):
                self.client.force_login(self.owner)
                response=self.client.post(self.url,self.payload(username='staff_'+role,role=role))
                self.assertEqual(response.status_code,302)
                grant=Membership.objects.get(user__username='staff_'+role)
                for permission in expected:
                    self.assertTrue(getattr(grant,permission),permission)
                self.assertFalse(grant.can_dispatch_on_debt)
        self.assertEqual(Membership.objects.count(),4)

    def test_cross_organization_facility_is_rejected(self):
        self.client.force_login(self.owner)
        response=self.client.post(self.url,self.payload(facility=self.foreign.pk))
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'boshqa tashkilotga tegishli')
        self.assertFalse(self.User.objects.filter(username='newstaff').exists())

    def test_invalid_branch_or_disabled_branch_rejected(self):
        self.client.force_login(self.owner)
        self.f1.is_active=False
        self.f1.save()
        response=self.client.post(self.url,self.payload(facility=self.f1.pk))
        self.assertEqual(response.status_code,200)
        self.assertFalse(self.User.objects.filter(username='newstaff').exists())

    def test_reject_duplicate_username_case_insensitively(self):
        self.client.force_login(self.owner)
        response=self.client.post(self.url,self.payload(username='SIMPLE_KEEPER'))
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'login band')
        self.assertFalse(Membership.objects.filter(user__username='SIMPLE_KEEPER').exists())

    def test_password_validation_and_mismatch(self):
        self.client.force_login(self.owner)
        weak=self.payload()
        weak['staff-password1']=weak['staff-password2']='password'
        self.assertEqual(self.client.post(self.url,weak).status_code,200)
        mismatch=self.payload()
        mismatch['staff-password2']='WrongDifferent!Password'
        self.assertEqual(self.client.post(self.url,mismatch).status_code,200)
        self.assertFalse(self.User.objects.filter(username='newstaff').exists())

    def test_revoke_and_reactivate_are_superadmin_only(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(self.url,self.payload(facility=self.f1.pk)).status_code,302)
        employee=self.User.objects.get(username='newstaff')
        grant=Membership.objects.get(user=employee)
        revoke=self.client.post(self.url,{'action':'revoke','membership_id':grant.pk})
        self.assertEqual(revoke.status_code,302)
        grant.refresh_from_db()
        self.assertFalse(grant.is_active)
        self.assertFalse(access.cameras(employee).exists())
        restore=self.client.post(self.url,{'action':'activate','membership_id':grant.pk})
        self.assertEqual(restore.status_code,302)
        grant.refresh_from_db()
        self.assertTrue(grant.is_active)
        self.assertEqual(list(access.cameras(employee).values_list('pk',flat=True)),[self.c1.pk])
        self.client.force_login(self.nonadmin)
        self.assertEqual(self.client.post(self.url,{'action':'revoke','membership_id':grant.pk}).status_code,403)

    def test_csrf_and_method_guard(self):
        browser=Client(enforce_csrf_checks=True)
        browser.force_login(self.owner)
        self.assertEqual(browser.post(self.url,self.payload()).status_code,403)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.put(self.url).status_code,405)
        self.assertFalse(self.User.objects.filter(username='newstaff').exists())

    def test_member_cannot_revoke_superuser_membership(self):
        membership=Membership.objects.create(user=self.owner,organization=self.org,role='director')
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(self.url,{'action':'revoke','membership_id':membership.pk}).status_code,403)
        membership.refresh_from_db()
        self.assertTrue(membership.is_active)

    def test_staff_view_hides_other_accounts_from_nonadmin(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(self.url,self.payload()).status_code,302)
        self.client.force_login(self.nonadmin)
        self.assertEqual(self.client.get(self.url+'?organization='+str(self.org.pk)).status_code,403)
