"""Enable only the three scheduled reports for the verified staging test organization.
Never enable camera alerts. Run once and remove temporary Railway service afterwards.
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand,CommandError
from warehouse.management.commands.seed_staging_demo import must_be_staging
from warehouse.notification_controls import current_controls,set_enabled
from warehouse.models import TelegramAlertDestination

ORG_CODE='test-agrostar-holadelnik'
VERIFIED_CHAT='-1004316868592'

class Command(BaseCommand):
    help='STAGING only: enable 08/14/20 reports, preserve disabled temperature alerts.'
    def add_arguments(self,parser):
        parser.add_argument('--apply',action='store_true')
    def handle(self,*args,**options):
        must_be_staging()
        root=get_user_model().objects.filter(is_superuser=True,is_active=True).order_by('pk').first()
        if root is None:
            raise CommandError('STAGING Super Admin hisobini topib bo‘lmadi')
        route=TelegramAlertDestination.objects.select_related('organization').filter(
            organization__code=ORG_CODE,organization__is_active=True,
            chat_id=VERIFIED_CHAT,enabled=True,daily_digest_enabled=True
        ).first()
        if route is None:
            raise CommandError('Sinov tashkiloti, tekshirilgan chat ID yoki uch mahal hisobot yoqilishi mos emas')
        old=current_controls()
        if old.alerts_enabled:
            raise CommandError('Kamera ogohlantirishlari o‘chiq emas; xavfsizlik uchun davom etilmaydi')
        if not options['apply']:
            self.stdout.write('STAGING REPORTS PRECHECK OK: reports can be enabled, alerts remain OFF')
            return
        set_enabled('reports',True,root)
        new=current_controls()
        if not new.reports_enabled or new.alerts_enabled:
            raise CommandError('Pauza holati kutilgancha yangilanmadi')
        self.stdout.write('STAGING REPORTS ENABLED: 08:00,14:00,20:00 Asia/Tashkent; CAMERA ALERTS DISABLED; test group configured')
