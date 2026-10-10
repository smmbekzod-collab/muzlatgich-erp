"""Multi-branch regression tests; run with Django's test runner in a test database."""
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError, PermissionDenied
from django.test import TestCase
from core.models import Organization, Facility, Camera, Membership
from core import access

class FacilityTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser('root-f', password='Long-Root-Password-123!')
        self.user = get_user_model().objects.create_user('keeper-f', password='Long-Keeper-Password-123!', is_staff=True)
        self.other = get_user_model().objects.create_user('other-f', password='Long-Other-Password-123!', is_staff=True)
        self.org = Organization.objects.create(name='Vodiy ombor', code='vodiy', camera_limit=10)
        self.foreign_org = Organization.objects.create(name='Toshkent ombor', code='toshkent', camera_limit=10)
        self.branch1 = Facility.objects.create(organization=self.org, name='Oltiariq', code='oltiariq', region='Farg‘ona')
        self.branch2 = Facility.objects.create(organization=self.org, name='Quva', code='quva')
        self.foreign_branch = Facility.objects.create(organization=self.foreign_org, name='Toshkent', code='toshkent')
        self.c1 = Camera.objects.create(organization=self.org, facility=self.branch1, number=1, capacity_kg=5000)
        self.c2 = Camera.objects.create(organization=self.org, facility=self.branch2, number=2, capacity_kg=5000)
        self.c3 = Camera.objects.create(organization=self.foreign_org, facility=self.foreign_branch, number=1)
        self.grant = Membership.objects.create(user=self.user, organization=self.org, all_cameras=True, all_facilities=False, can_receive=True)
        self.grant.facilities.add(self.branch1)

    def test_filial_permission_is_scoped_on_server(self):
        self.assertEqual(list(access.cameras(self.user).values_list('id', flat=True)), [self.c1.pk])
        self.assertEqual(list(access.facilities(self.user).values_list('id', flat=True)), [self.branch1.pk])
        with self.assertRaises(PermissionDenied):
            access.authorize(self.user, self.org.pk, self.c2.pk, 'receive')
        with self.assertRaises(PermissionDenied):
            access.authorize(self.user, self.foreign_org.pk, self.c3.pk, 'receive')

    def test_all_facilities_grant_and_new_branch(self):
        self.grant.all_facilities = True
        self.grant.save()
        self.assertEqual(set(access.cameras(self.user).values_list('pk',flat=True)), {self.c1.pk,self.c2.pk})
        new = Facility.objects.create(organization=self.org, name='Bog‘dod', code='bogdod')
        new_cam = Camera.objects.create(organization=self.org, facility=new, number=3)
        self.assertIn(new_cam.pk, access.cameras(self.user).values_list('pk',flat=True))

    def test_camera_cannot_belong_to_wrong_tenant(self):
        with self.assertRaises(ValidationError):
            Camera.objects.create(organization=self.org, facility=self.foreign_branch, number=5)

    def test_legacy_camera_gets_default_facility(self):
        cam = Camera.objects.create(organization=self.org, number=6)
        self.assertEqual(cam.facility.organization_id, self.org.pk)
        self.assertEqual(cam.facility.code, 'main')

    def test_cannot_reassign_org_or_branch_for_audited_facility(self):
        self.branch1.organization = self.foreign_org
        with self.assertRaises(ValidationError):
            self.branch1.save()

    def test_company_admin_cannot_create_facility(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.post('/admin/core/facility/add/', {
            'organization': self.org.pk, 'name': 'Qo‘shilgan', 'code':'new'
        }).status_code, 403)

    def test_dashboard_facility_filter_does_not_leak(self):
        self.client.force_login(self.user)
        response = self.client.get('/app/?facility='+str(self.foreign_branch.pk))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Toshkent ombor')
        self.assertNotContains(response, 'Quva')

    def test_membership_form_rejects_foreign_facility(self):
        from core.forms import MembershipForm
        form = MembershipForm(data={
            'user':self.user.pk,'organization':self.org.pk,
            'role':'keeper','all_cameras':'on','facilities':[self.foreign_branch.pk],
            'all_facilities':'','cameras':[]
        }, instance=self.grant)
        self.assertFalse(form.is_valid())
        self.assertIn('facilities', form.errors)
