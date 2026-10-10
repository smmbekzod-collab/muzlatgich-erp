"""3x daily scheduled Telegram digest: tenant isolation, idempotency, exact slots, retries."""
from datetime import datetime, timedelta
from decimal import Decimal as D
from unittest.mock import patch
from zoneinfo import ZoneInfo
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase,override_settings
from core.models import Organization,Facility,Camera
from warehouse.models import (
    Lot,Operation,DailyTelegramDigest,TelegramAlertDestination,
    CameraEnvironmentAlert,CameraEnvironmentPolicy)
from warehouse.daily_digests import (
    UZ_TZ,summary_window,compose_organization_report,enqueue_slot,drain_digests)


@override_settings(
    STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},
              'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class ThreeTimesDailyReportTests(TestCase):
    def setUp(self):
        U=get_user_model()
        self.root=U.objects.create_superuser('digest_root',password='DemoStrongTest!123123')
        self.one=Organization.objects.create(name='TEST — Tashkilot A',code='digest-a')
        self.two=Organization.objects.create(name='TEST — Tashkilot B',code='digest-b')
        f=Facility.objects.create(organization=self.one,name='Birinchi filial',code='a')
        g=Facility.objects.create(organization=self.two,name='Ikkinchi filial',code='b')
        self.cam=Camera.objects.create(organization=self.one,facility=f,number=1)
        self.cam2=Camera.objects.create(organization=self.two,facility=g,number=1)
        self.route=TelegramAlertDestination.objects.create(
            organization=self.one,chat_id='-10011111',enabled=True,updated_by=self.root)
        self.route2=TelegramAlertDestination.objects.create(
            organization=self.two,chat_id='-10022222',enabled=True,updated_by=self.root)
        self.today=datetime(2026,10,12,8,0,tzinfo=UZ_TZ).date()

    def now(self,hour,minute=5):
        return datetime.combine(self.today,datetime.min.time(),tzinfo=UZ_TZ).replace(hour=hour,minute=minute)

    def test_slot_windows_handle_overnight_and_dayparts(self):
        self.assertEqual(summary_window(self.today,8),datetime(2026,10,11,20,tzinfo=UZ_TZ))
        self.assertEqual(summary_window(self.today,14),datetime(2026,10,12,8,tzinfo=UZ_TZ))
        self.assertEqual(summary_window(self.today,20),datetime(2026,10,12,14,tzinfo=UZ_TZ))

    def test_three_messages_per_day_not_one_or_four(self):
        for hour in (8,14,20):
            count=enqueue_slot(hour,now=self.now(hour))
            self.assertEqual(count,2)
            self.assertEqual(enqueue_slot(hour,now=self.now(hour,minute=25)),0)
        self.assertEqual(DailyTelegramDigest.objects.count(),6)
        self.assertEqual(
            list(DailyTelegramDigest.objects.filter(organization=self.one)
                .order_by('slot_hour').values_list('slot_hour',flat=True)),
            [8,14,20])
        for hour in (8,14,20):
            self.assertTrue(DailyTelegramDigest.objects.filter(
                organization=self.one,report_date=self.today,slot_hour=hour).exists())

    def test_wrong_hour_rejected_without_data(self):
        with self.assertRaises(ValueError):
            enqueue_slot(8,now=self.now(14))
        with self.assertRaises(ValueError):
            enqueue_slot(7,now=self.now(7))
        self.assertEqual(DailyTelegramDigest.objects.count(),0)

    def test_disabled_routes_not_queued(self):
        self.route2.daily_digest_enabled=False
        self.route2.save(update_fields=['daily_digest_enabled'])
        self.assertEqual(enqueue_slot(8,now=self.now(8)),1)
        self.assertEqual(list(DailyTelegramDigest.objects.values_list(
            'organization_id',flat=True)),[self.one.id])

    def test_report_does_not_include_other_company_name_or_data(self):
        other_only='VERY PRIVATE INVENTORY ZZZ'
        from warehouse.models import Customer
        import uuid
        c=Customer.objects.create(organization=self.two,name='Other company client')
        Lot.objects.create(
            id=uuid.uuid4(),create_key=uuid.uuid4(),organization=self.two,
            camera=self.cam2,customer=c,product=other_only,
            variety='',box_type='test',received_on=self.today,
            last_stock_date=self.today,initial_boxes=14,boxes=14,
            initial_gross=D('140'),initial_tare=D('14'),
            gross=D('140'),tare=D('14'),
            tariff_name='test',service='tiered',basis='net',
            rate=D('200'),storage_mode='prorata',created_by=self.root)
        a=compose_organization_report(self.one,self.today,8,now=self.now(8))
        b=compose_organization_report(self.two,self.today,8,now=self.now(8))
        self.assertIn('Tashkilot A',a)
        self.assertNotIn('Tashkilot B',a)
        self.assertIn('Tashkilot B',b)
        self.assertIn('14 ta',b)
        self.assertNotIn('14 ta',a)

    @patch.dict('os.environ',{'TELEGRAM_BOT_TOKEN':'123:testing'},clear=False)
    @patch('warehouse.daily_digests.sleeper.sleep')
    @patch('warehouse.daily_digests.send_message')
    def test_one_bot_delivers_to_separate_groups(self,send,sleep):
        self.assertEqual(enqueue_slot(8,now=self.now(8)),2)
        result=drain_digests(now=self.now(8,10))
        self.assertEqual(result['sent'],2)
        groups={call.args[1] for call in send.call_args_list}
        self.assertEqual(groups,{'-10011111','-10022222'})
        mapping={call.args[1]:call.args[2] for call in send.call_args_list}
        self.assertIn('Tashkilot A',mapping['-10011111'])
        self.assertNotIn('Tashkilot B',mapping['-10011111'])
        self.assertIn('Tashkilot B',mapping['-10022222'])
        self.assertNotIn('Tashkilot A',mapping['-10022222'])
        self.assertEqual(drain_digests(now=self.now(8,11))['sent'],0)
        self.assertEqual(send.call_count,2)

    @patch.dict('os.environ',{'TELEGRAM_BOT_TOKEN':'123:testing'},clear=False)
    @patch('warehouse.daily_digests.send_message')
    def test_disabled_or_changed_chat_does_not_get_report(self,send):
        enqueue_slot(8,now=self.now(8))
        self.route.enabled=False
        self.route.save(update_fields=['enabled'])
        # Do not send old A digest to B or an unconfigured destination.
        result=drain_digests(now=self.now(8,12))
        self.assertEqual(result['sent'],1)
        self.assertEqual(send.call_args.args[1],self.route2.chat_id)
        a=DailyTelegramDigest.objects.get(organization=self.one)
        self.assertEqual(a.delivery_status,'disabled')

    @patch.dict('os.environ',{'TELEGRAM_BOT_TOKEN':'123:testing'},clear=False)
    @patch('warehouse.daily_digests.sleeper.sleep')
    @patch('warehouse.daily_digests.send_message',side_effect=RuntimeError('Telegram HTTP 429'))
    def test_failed_digest_remains_for_retry(self,send,sleep):
        self.route2.enabled=False
        self.route2.save(update_fields=['enabled'])
        enqueue_slot(14,now=self.now(14))
        r=drain_digests(now=self.now(14,2))
        self.assertEqual(r['failed'],1)
        item=DailyTelegramDigest.objects.get(organization=self.one)
        self.assertEqual(item.attempts,1)
        self.assertEqual(item.delivery_status,'failed')
        self.assertIsNotNone(item.next_attempt_at)
        self.assertEqual(drain_digests(now=self.now(14,3))['failed'],0)

    def test_shared_active_chat_is_rejected(self):
        self.route2.chat_id=self.route.chat_id
        with self.assertRaises(ValidationError):self.route2.full_clean()

    def test_message_reports_zero_values_and_no_hardcoded_prices(self):
        message=compose_organization_report(self.one,self.today,8,now=self.now(8))
        self.assertIn('08:00 HISOBOT',message)
        self.assertIn('Qolgan yashiklar: 0 ta',message)
        self.assertIn('Jami qarz: 0 so‘m',message)
        self.assertIn('TEST MA’LUMOTLARI',message)
        self.assertLess(len(message),4096)


    def test_group_cannot_be_assigned_to_second_organization(self):
        from django.urls import reverse
        self.client.force_login(self.root)
        response=self.client.post(reverse('telegram_destinations'),{
            'organization':self.two.pk,'chat_id':self.route.chat_id,
            'enabled':'on','daily_digest_enabled':'on'})
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'boshqa faol tashkilotga tegishli')
        self.route2.refresh_from_db()
        self.assertEqual(self.route2.chat_id,'-10022222')
        self.assertTrue(self.route2.enabled)

    def test_disabling_digest_preserves_alerts_but_blocks_future_reports(self):
        from django.urls import reverse
        self.client.force_login(self.root)
        response=self.client.post(reverse('telegram_destinations'),{
            'organization':self.one.pk,'chat_id':self.route.chat_id,
            'enabled':'on'})
        self.assertEqual(response.status_code,302)
        self.route.refresh_from_db()
        self.assertTrue(self.route.enabled)
        self.assertFalse(self.route.daily_digest_enabled)
        self.assertEqual(enqueue_slot(8,now=self.now(8)),1)
        self.assertFalse(DailyTelegramDigest.objects.filter(organization=self.one).exists())
