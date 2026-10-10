"""One TEST Telegram digest for the previously verified test group, never a scheduled slot."""
import os
from datetime import timedelta
from zoneinfo import ZoneInfo
from django.core.management.base import BaseCommand,CommandError
from django.utils import timezone
from core.models import Organization
from warehouse.models import TelegramAlertDestination
from warehouse.daily_digests import compose_organization_report,UZ_TZ
from warehouse.telegram_sender import send_message
from warehouse.management.commands.seed_staging_demo import must_be_staging


class Command(BaseCommand):
    help='STAGING only: send one marked sample financial report to the verified TEST group.'
    def add_arguments(self,parser):
        parser.add_argument('--apply',action='store_true')
    def handle(self,*args,**opts):
        must_be_staging()
        org=Organization.objects.filter(code='test-agrostar-holadelnik',is_active=True).first()
        if not org or not org.name.startswith('TEST'):
            raise CommandError('TEST organization not available')
        route=TelegramAlertDestination.objects.filter(organization=org,
            enabled=True,daily_digest_enabled=True,chat_id='-1004316868592').first()
        if not route:
            raise CommandError('Verified TEST group route or report opt-in is missing')
        now=timezone.now()
        local=timezone.localtime(now,UZ_TZ)
        report_date=local.date()
        if local.hour>=20:hour=20
        elif local.hour>=14:hour=14
        elif local.hour>=8:hour=8
        else:
            hour=20
            report_date-=timedelta(days=1)
        preview=compose_organization_report(org,report_date,hour,now)
        preview=preview.replace(f'— {hour:02d}:00 HISOBOT',
            f'— NAMUNAVIY HISOBOT ({local:%H:%M})',1)
        preview=('🧪 REJADAN TASHQARI SINOV — JADVALNI ALMASHTIRMAYDI\n\n'+preview)[:4000]
        if not opts['apply']:
            self.stdout.write('TEST REPORT PREVIEW VALID: '+str(len(preview))+' chars. No Telegram message sent.')
            return
        token=os.environ.get('TELEGRAM_BOT_TOKEN','').strip()
        send_message(token,route.chat_id,preview)
        self.stdout.write('SAMPLE DIGEST SENT: chat verified, report length='+str(len(preview)))
