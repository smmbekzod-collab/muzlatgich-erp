from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.contrib.admin.models import LogEntry
from django.core.exceptions import PermissionDenied, ValidationError
from .models import Organization, Camera, Membership
from .forms import MembershipForm
from .access import authorize, cameras

@override_settings(STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class AccessTests(TestCase):
    def setUp(self):
        self.root=get_user_model().objects.create_superuser('root',password='Long-Root-Pass-431!')
        self.user=get_user_model().objects.create_user('keeper',password='Long-Keeper-Pass-931!',is_staff=True)
        self.a=Organization.objects.create(name='Tashkilot A',code='org-a',camera_limit=2)
        self.b=Organization.objects.create(name='Yashirin tashkilot B',code='org-b',camera_limit=20)
        self.a1=Camera.objects.create(organization=self.a,number=1)
        self.a2=Camera.objects.create(organization=self.a,number=2)
        self.b1=Camera.objects.create(organization=self.b,number=1,name='Maxfiy kamera')
        self.grant=Membership.objects.create(user=self.user,organization=self.a,can_receive=True)
        self.grant.cameras.add(self.a1)
        self.client.force_login(self.user)

    def test_tenant_camera_scope(self):
        self.assertEqual(list(cameras(self.user).values_list('pk',flat=True)),[self.a1.pk])
    def test_cross_tenant_denied(self):
        with self.assertRaises(PermissionDenied):authorize(self.user,self.b.pk,self.b1.pk,'receive')
    def test_wrong_org_even_super_denied(self):
        with self.assertRaises(PermissionDenied):authorize(self.root,self.a.pk,self.b1.pk,'receive')
    def test_unassigned_camera_denied(self):
        with self.assertRaises(PermissionDenied):authorize(self.user,self.a.pk,self.a2.pk,'receive')
    def test_granted_action_works(self):
        self.assertEqual(authorize(self.user,self.a.pk,self.a1.pk,'receive'),self.a1)
    def test_ungranted_action_denied(self):
        with self.assertRaises(PermissionDenied):authorize(self.user,self.a.pk,self.a1.pk,'payment')
    def test_revocation_immediate(self):
        self.grant.is_active=False;self.grant.save()
        with self.assertRaises(PermissionDenied):authorize(self.user,self.a.pk,self.a1.pk,'receive')
        self.assertEqual(self.client.get('/admin/').status_code,302)
    def test_disabled_org_denied(self):
        self.a.is_active=False;self.a.save()
        with self.assertRaises(PermissionDenied):authorize(self.user,self.a.pk,self.a1.pk,'receive')
    def test_disabled_camera_denied(self):
        self.a1.is_active=False;self.a1.save()
        with self.assertRaises(PermissionDenied):authorize(self.user,self.a.pk,self.a1.pk,'receive')
    def test_disabled_user_denied(self):
        self.user.is_active=False;self.user.save()
        with self.assertRaises(PermissionDenied):authorize(self.user,self.a.pk,self.a1.pk,'receive')
    def test_admin_cannot_add_camera(self):
        self.assertEqual(self.client.post('/admin/core/camera/add/',{'organization':self.a.pk,'number':3}).status_code,403)
    def test_admin_cannot_grant_self_permission(self):
        self.assertEqual(self.client.post(f'/admin/core/membership/{self.grant.pk}/change/',{'can_take_payment':'on'}).status_code,403)
        self.grant.refresh_from_db();self.assertFalse(self.grant.can_take_payment)
    def test_admin_cannot_edit_users(self):
        self.assertEqual(self.client.post(f'/admin/auth/user/{self.user.pk}/change/',{'is_superuser':'on'}).status_code,403)
    def test_admin_cannot_edit_camera(self):
        self.assertEqual(self.client.post(f'/admin/core/camera/{self.a1.pk}/change/',{'name':'hacked'}).status_code,403)
    def test_list_does_not_leak_other_tenant(self):
        response=self.client.get('/admin/core/camera/')
        self.assertEqual(response.status_code,200)
        self.assertNotContains(response,'Maxfiy kamera')
        self.assertNotContains(response,'Yashirin tashkilot B')
    def test_direct_other_tenant_object_hidden(self):
        response=self.client.get(f'/admin/core/camera/{self.b1.pk}/change/')
        self.assertIn(response.status_code,[302,403,404])
        self.assertNotIn(b'Maxfiy kamera',response.content)
    def test_quota_enforced(self):
        with self.assertRaises(ValidationError):Camera.objects.create(organization=self.a,number=3)
    def test_quota_cannot_be_lowered_below_inventory(self):
        self.a.camera_limit=1
        with self.assertRaises(ValidationError):self.a.save()
    def test_camera_cannot_move_tenant(self):
        self.a1.organization=self.b
        with self.assertRaises(ValidationError):self.a1.save()
    def test_duplicate_camera_number(self):
        with self.assertRaises(ValidationError):Camera.objects.create(organization=self.b,number=1)
    def test_same_number_other_org_allowed(self):
        self.assertEqual(self.a1.number,self.b1.number)
    def test_grant_cannot_select_other_org_camera(self):
        form=MembershipForm(data={'user':self.user.pk,'organization':self.a.pk,'role':'admin','cameras':[self.b1.pk]},instance=self.grant)
        self.assertFalse(form.is_valid());self.assertIn('cameras',form.errors)
    def test_debt_requires_dispatch(self):
        self.grant.can_dispatch_on_debt=True
        with self.assertRaises(ValidationError):self.grant.full_clean()
    def test_all_cameras_includes_new_camera(self):
        self.grant.all_cameras=True;self.grant.save()
        self.a.camera_limit=3;self.a.save()
        new=Camera.objects.create(organization=self.a,number=3)
        self.assertEqual(authorize(self.user,self.a.pk,new.pk,'receive'),new)
    def test_super_dashboard_and_audited_create(self):
        self.client.force_login(self.root)
        self.assertContains(self.client.get('/admin/'),'Super admin')
        response=self.client.post('/admin/core/camera/add/',{'organization':self.b.pk,'number':2,'name':'Yangi','is_active':'on','_save':'Save'})
        self.assertEqual(response.status_code,302)
        self.assertTrue(Camera.objects.filter(organization=self.b,number=2).exists())
        self.assertTrue(LogEntry.objects.filter(user=self.root,action_flag=1).exists())
    def test_unknown_operation_denied(self):
        with self.assertRaises(PermissionDenied):authorize(self.root,self.a.pk,self.a1.pk,'grant_superuser')
