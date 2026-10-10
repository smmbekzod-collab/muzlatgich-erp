"""One-time staging-only pause all Telegram report and alert sends.

This does not stop Railway cron startup costs: it stops DB report preparation and
Telegram HTTP requests. Railway schedules can be suspended separately in the
Railway dashboard to eliminate cron executions.
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand,CommandError
from warehouse.management.commands.seed_staging_demo import must_be_staging
from warehouse.notification_controls import set_enabled,current_controls


class Command(BaseCommand):
    help='STAGING only: temporarily pause all reports and camera Telegram sends.'
    def add_arguments(self,parser):
        parser.add_argument('--apply',action='store_true')
    def handle(self,*args,**options):
        must_be_staging()
        root=get_user_model().objects.filter(is_superuser=True,is_active=True).order_by('pk').first()
        if not root:
            raise CommandError('STAGING Super Admin topilmadi')
        if not options['apply']:
            self.stdout.write('STAGING telegram pause dry-run. No data changed.')
            return
        set_enabled('reports',False,root)
        set_enabled('alerts',False,root)
        state=current_controls()
        if state.reports_enabled or state.alerts_enabled:
            raise CommandError('Pauza saqlanmadi')
        self.stdout.write('STAGING TELEGRAM PAUSED: reports=OFF, alerts=OFF, no Telegram sends')
