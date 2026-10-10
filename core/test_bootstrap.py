import hashlib
import os
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

_CODE = 'one-time-test-only-strong-code-12345'
_ENV = {'ENABLE_STAGING_SETUP': '1',
        'STAGING_SETUP_CODE_SHA256': hashlib.sha256(_CODE.encode()).hexdigest()}

@override_settings(STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},
                            'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class InitialAdminSetupTests(TestCase):
    url = '/setup/'

    def payload(self, code=_CODE, username='initialadmin', password='VeryStrong!879-Unique'):
        return {'setup_code':code,'username':username,
                'password1':password,'password2':password}

    def test_is_disabled_without_railway_environment_guard(self):
        with patch.dict(os.environ,{},clear=True):
            self.assertEqual(self.client.get(self.url).status_code,404)
            self.assertEqual(self.client.post(self.url,self.payload()).status_code,404)

    @patch.dict(os.environ,_ENV)
    def test_get_shows_mobile_form_but_never_exposes_otp(self):
        response=self.client.get(self.url)
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'Super Admin hisobini yarating')
        self.assertNotContains(response,_CODE)
        self.assertEqual(response['Cache-Control'].lower().split(',')[0],'max-age=0')

    @patch.dict(os.environ,_ENV)
    def test_wrong_code_does_not_create_user(self):
        response=self.client.post(self.url,self.payload(code='incorrect'))
        self.assertEqual(response.status_code,200)
        self.assertFalse(get_user_model().objects.exists())
        self.assertContains(response,'Ma’lumotlarni tekshiring')

    @patch.dict(os.environ,_ENV)
    def test_requires_secure_password_and_matching_confirmation(self):
        info=self.payload(password='123')
        response=self.client.post(self.url,info)
        self.assertEqual(response.status_code,200)
        self.assertFalse(get_user_model().objects.exists())
        info=self.payload()
        info['password2']='NotMatching!123'
        response=self.client.post(self.url,info)
        self.assertEqual(response.status_code,200)
        self.assertFalse(get_user_model().objects.exists())

    @patch.dict(os.environ,_ENV)
    def test_creates_single_superadmin_logs_in_and_disables_setup(self):
        info=self.payload()
        r=self.client.post(self.url,info)
        self.assertEqual(r.status_code,302)
        self.assertEqual(r.url,'/app/')
        user=get_user_model().objects.get(username='initialadmin')
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.check_password(info['password1']))
        self.assertEqual(self.client.get(self.url).status_code,404)
        self.assertEqual(self.client.post(self.url,self.payload(username='another')).status_code,404)

    @patch.dict(os.environ,_ENV)
    def test_existing_superuser_blocks_setup_even_with_code(self):
        get_user_model().objects.create_superuser('existing',password='StrongExisting!1234')
        self.assertEqual(self.client.get(self.url).status_code,404)
        self.assertEqual(self.client.post(self.url,self.payload()).status_code,404)

    @patch.dict(os.environ,_ENV)
    def test_csrf_is_required(self):
        from django.test import Client
        client=Client(enforce_csrf_checks=True)
        self.assertEqual(client.post(self.url,self.payload()).status_code,403)
