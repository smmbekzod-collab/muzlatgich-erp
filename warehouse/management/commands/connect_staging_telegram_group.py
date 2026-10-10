"""Safely connect a verified Telegram test supergroup in isolated STAGING.

A group invite URL does not expose its numeric Telegram ID, so the ID must be
read from bot updates first. This command verifies the bot's administrator
membership and exact group title before any outbound message or DB write.

One-time apply is repeat-safe; does not touch production/main.
"""
import os
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand,CommandError
from django.db import transaction
from core.models import Organization
from warehouse.models import TelegramAlertDestination,CameraEnvironmentAlert
from warehouse.telegram_sender import send_message,drain_alerts
from .probe_test_group import api,STAGING_ID,EXPECTED_BOT
from .seed_staging_demo import must_be_staging

ORG='test-agrostar-holadelnik'
EXPECTED_TITLE='Muzlatgichtest'


class Command(BaseCommand):
    help='Staging only: verify bot is admin, send one TEST message, bind TEST org and deliver pending alerts.'
    def add_arguments(self,parser):
        parser.add_argument('--chat-id',required=True,type=int)
        parser.add_argument('--apply',action='store_true')
    def handle(self,*args,**options):
        must_be_staging()
        chat_id=options['chat_id']
        if chat_id>=0:raise CommandError('Guruh chat ID manfiy raqam bo‘lishi kerak.')
        me=api('getMe')
        if me.get('username','').lower()!=EXPECTED_BOT.lower():
            raise CommandError('Kutilgan test boti emas.')
        chat=api('getChat',{'chat_id':chat_id})
        if chat.get('type') not in ('supergroup','group'):
            raise CommandError('Telegram manzili guruh emas.')
        if chat.get('title','')!=EXPECTED_TITLE:
            raise CommandError('Telegram guruh nomi mos emas; xato chatga yuborilmaydi.')
        member=api('getChatMember',{'chat_id':chat_id,'user_id':me['id']})
        if member.get('status') not in ('administrator','creator'):
            raise CommandError('Bot guruhda administrator emas.')
        org=Organization.objects.filter(code=ORG,is_active=True).first()
        root=get_user_model().objects.filter(is_superuser=True,is_active=True).order_by('pk').first()
        if not (org and root):raise CommandError('Sinov tashkiloti yoki Super Admin topilmadi.')

        current=TelegramAlertDestination.objects.filter(organization=org).first()
        if current and current.chat_id!=str(chat_id):
            raise CommandError('Tashkilotga boshqa chat bog‘langan; avtomatik almashtirilmaydi.')
        if not options['apply']:
            self.stdout.write(f'VERIFIED ONLY: {EXPECTED_TITLE} chat_id={chat_id}; bot_admin=yes; no messages sent; DB unchanged')
            return
        if current is None or not current.enabled:
            token=os.environ.get('TELEGRAM_BOT_TOKEN','').strip()
            # Probe actual delivery BEFORE activating the route in the DB.
            send_message(token,str(chat_id),
                '✅ [TEST] Muzlatgich ERP 2.0\n'
                'Telegram guruhiga sinov xabari muvaffaqiyatli yo‘naltirildi.\n'
                'Tashkilot: TEST — Agro Star Muzlatkich ERP\n'
                'Bu haqiqiy mijoz yoki real ombor hodisasi emas.')
            test_sent=True
        else:
            test_sent=False
        with transaction.atomic():
            Organization.objects.select_for_update().get(pk=org.pk)
            destination,created=TelegramAlertDestination.objects.update_or_create(
                organization=org, defaults={
                    'chat_id':str(chat_id),'enabled':True,'updated_by':root})
            destination.full_clean()
            CameraEnvironmentAlert.objects.filter(
                camera__organization=org,resolved_at__isnull=True,
                delivery_status='disabled',sent_at__isnull=True).update(
                delivery_status='pending',next_attempt_at=None,last_error='')
        delivery=drain_alerts(limit=15)
        self.stdout.write(
            f'GROUP CONNECTED: title={EXPECTED_TITLE} chat_id={chat_id} '
            f'org={ORG} route_enabled=yes direct_test_sent={test_sent} '
            f'queued_alerts_sent={delivery["sent"]} failed={delivery["failed"]} '
            f'token_configured={not delivery["skipped"]}'
        )
