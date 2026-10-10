"""Regression tests: Super Admin Telegram pause buttons, scoped organization switches.

All network sending is mocked, CSRF required, and no real data is created.
"""
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch
from zoneinfo import ZoneInfo
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase,Client,override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import Organization,Facility,Camera
from warehouse.models import (
    PlatformNotificationControl,TelegramAlertDestination,DailyTelegramDigest,
    CameraEnvironmentAlert,CameraEnvironmentPolicy,CameraEnvironmentReading,
)
from warehouse.notification_controls import is_enabled
from warehouse.daily_digests import enqueue_slot,drain_digests
from warehouse.telegram_sender import drain_alerts
from warehouse.monitor_alerts import reconcile_camera


@override_settings(STORAGES={
    'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},
    'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}
})
class PlatformPauseTests(TestCase):
    def setUp(self):
        U=get_user_model()
        self.admin=U.objects.create_superuser('pause_admin',password='S3cure-test-12345')
        self.staff=U.objects.create_user('pause_staff',password='S3cure-test-12345',is_staff=True)
        self.org=Organization.objects.create(name='TEST organization A',code='pause-a')
        self.other=Organization.objects.create(name='TEST organization B',code='pause-b')
        branch=Facility.objects.create(organization=self.org,name='A',code='a')
        self.camera=Camera.objects.create(organization=self.org,facility=branch,number=1)
        self.route=TelegramAlertDestination.objects.create(
            organization=self.org,chat_id='-10030011',enabled=True,updated_by=self.admin)
        self.other_route=TelegramAlertDestination.objects.create(
            organization=self.other,chat_id='-10030022',enabled=True,updated_by=self.admin)
        self.url=reverse('telegram_destinations')
        self.local=datetime(2026,10,12,8,5,tzinfo=ZoneInfo('Asia/Tashkent'))

    def test_superadmin_only_toggle_and_csrf(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.post(self.url,{'action':'pause_reports'}).status_code,403)
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(self.url),'Hisobotlarni o‘chirish')
        browser=Client(enforce_csrf_checks=True)
        browser.force_login(self.admin)
        self.assertEqual(browser.post(self.url,{'action':'pause_reports'}).status_code,403)
        self.assertTrue(is_enabled('reports'))

    def test_global_report_pause_kills_queue_and_resume_keeps_old_disabled(self):
        self.assertEqual(enqueue_slot(8,now=self.local),2)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(self.url,{'action':'pause_reports'}).status_code,302)
        self.assertFalse(is_enabled('reports'))
        self.assertTrue(is_enabled('alerts'))
        self.assertEqual(enqueue_slot(8,now=self.local),0)
        self.assertEqual(DailyTelegramDigest.objects.filter(delivery_status='disabled').count(),2)
        with patch.dict('os.environ',{'TELEGRAM_BOT_TOKEN':'123:testing'},clear=False), \
             patch('warehouse.daily_digests.send_message') as send:
            result=drain_digests(now=self.local)
            self.assertEqual(result['sent'],0)
            send.assert_not_called()
        self.assertContains(self.client.get(self.url),'Hisobotlarni yoqish')
        self.assertEqual(self.client.post(self.url,{'action':'resume_reports'}).status_code,302)
        self.assertTrue(is_enabled('reports'))
        self.assertTrue(DailyTelegramDigest.objects.filter(
            delivery_status='disabled').count()==2)
        self.assertEqual(enqueue_slot(14,now=self.local.replace(hour=14)),2)

    def test_alerts_pause_blocks_send_and_resumed_new_incident_sent(self):
        CameraEnvironmentPolicy.objects.create(
            camera=self.camera,updated_by=self.admin,
            min_temperature=Decimal('-1'),max_temperature=Decimal('2'))
        CameraEnvironmentReading.objects.create(
            camera=self.camera,measured_at=timezone.now()-timedelta(minutes=2),
            temperature=Decimal('6'),humidity=Decimal('80'),recorded_by=self.admin)
        reconcile_camera(self.camera.pk)
        self.assertEqual(CameraEnvironmentAlert.objects.filter(
            delivery_status='pending').count(),1)
        self.client.force_login(self.admin)
        self.client.post(self.url,{'action':'pause_alerts'})
        self.assertFalse(is_enabled('alerts'))
        self.assertEqual(CameraEnvironmentAlert.objects.get().delivery_status,'disabled')
        with patch.dict('os.environ',{'TELEGRAM_BOT_TOKEN':'123:testing'},clear=False), \
             patch('warehouse.telegram_sender.send_message') as send:
            self.assertEqual(drain_alerts()['sent'],0)
            send.assert_not_called()
        self.client.post(self.url,{'action':'resume_alerts'})
        self.assertTrue(is_enabled('alerts'))
        reconcile_camera(self.camera.pk)
        self.assertEqual(CameraEnvironmentAlert.objects.get().delivery_status,'pending')
        with patch.dict('os.environ',{'TELEGRAM_BOT_TOKEN':'123:testing'},clear=False), \
             patch('warehouse.telegram_sender.send_message') as send:
            self.assertEqual(drain_alerts()['sent'],1)
            self.assertEqual(send.call_args.args[1],self.route.chat_id)

    def test_scoped_tenant_toggle_does_not_change_other_chat_or_alert_enabled(self):
        self.client.force_login(self.admin)
        res=self.client.post(self.url,{'action':'toggle_org_reports',
             'organization_id':str(self.org.pk)})
        self.assertEqual(res.status_code,302)
        self.route.refresh_from_db()
        self.other_route.refresh_from_db()
        self.assertFalse(self.route.daily_digest_enabled)
        self.assertTrue(self.route.enabled)
        self.assertTrue(self.other_route.daily_digest_enabled)
        self.assertEqual(enqueue_slot(8,now=self.local),1)
        self.assertEqual(list(DailyTelegramDigest.objects.values_list(
            'organization_id',flat=True)),[self.other.pk])
        self.client.post(self.url,{'action':'toggle_org_reports',
             'organization_id':str(self.org.pk)})
        self.route.refresh_from_db()
        self.assertTrue(self.route.daily_digest_enabled)
        self.assertEqual(enqueue_slot(14,now=self.local.replace(hour=14)),2)

    def test_unknown_or_missing_org_cannot_change_settings(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(self.url,{'action':'toggle_org_reports',
            'organization_id':'bad'}).status_code,403)
        self.assertEqual(self.client.post(self.url,{'action':'toggle_org_reports',
            'organization_id':'99999'}).status_code,403)
        self.assertEqual(self.client.post(self.url,{'action':'toggle_org_reports',
            'organization_id':str(self.other.pk)}).status_code,302)

    @patch('warehouse.management.commands.process_monitor_alerts.scan_all_cameras')
    @patch('warehouse.daily_digests.send_message')
    @patch('warehouse.telegram_sender.send_message')
    def test_both_off_cron_skips_monitor_scan_and_network(self,sends_alert,sends_digest,scan):
        self.client.force_login(self.admin)
        self.client.post(self.url,{'action':'pause_reports'})
        self.client.post(self.url,{'action':'pause_alerts'})
        call_command('process_monitor_alerts','--limit=50')
        scan.assert_not_called()
        sends_alert.assert_not_called()
        sends_digest.assert_not_called()
