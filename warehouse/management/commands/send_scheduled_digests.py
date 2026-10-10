"""Railway UTC cron: 0 3,9,15 * * * equals 08,14,20 Asia/Tashkent."""
from django.core.management.base import BaseCommand,CommandError
from django.utils import timezone
from zoneinfo import ZoneInfo
from warehouse.daily_digests import SLOTS,enqueue_slot,drain_digests


class Command(BaseCommand):
    help='Har kuni 08:00, 14:00 va 20:00 da har tashkilotga alohida Telegram hisobot.'
    def handle(self,*args,**options):
        local=timezone.localtime(timezone.now(),ZoneInfo('Asia/Tashkent'))
        if local.hour not in SLOTS:
            raise CommandError('Hozir rejalashtirilgan mahalliy hisobot soati emas')
        made=enqueue_slot(local.hour)
        out=drain_digests(limit=200)
        self.stdout.write(
            f'DIGEST {local:%Y-%m-%d %H:%M} Toshkent; '
            f'new={made} sent={out["sent"]} failed={out["failed"]} '
            f'token_present={not out["skipped"]}')
