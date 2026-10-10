from django.core.management.base import BaseCommand
from warehouse.monitor_alerts import scan_all_cameras
from warehouse.telegram_sender import drain_alerts
from warehouse.daily_digests import drain_digests
from warehouse.notification_controls import is_enabled


class Command(BaseCommand):
    help='Kameralar me’yorini tekshiradi va Telegram navbatini yuboradi. Cron orqali ishga tushiring.'
    def add_arguments(self,parser):
        parser.add_argument('--limit',type=int,default=10000,help='Tekshiriladigan kamera soni')
        parser.add_argument('--send-limit',type=int,default=30,help='Har safar yuboriladigan xabarlar soni')
    def handle(self,*args,**options):
        camera_limit=max(1,min(100000,options['limit']))
        send_limit=max(0,min(100,options['send_limit']))
        if not is_enabled('alerts') and not is_enabled('reports'):
            self.stdout.write('TELEGRAM PAUSE: barcha yuborishlar o‘chiq; tekshiruv va tarmoq chaqirilmaydi')
            return
        if is_enabled('alerts'):
            checked,new=scan_all_cameras(max_cameras=camera_limit)
            result=drain_alerts(limit=send_limit)
        else:
            checked=new=0
            result={'sent':0,'failed':0,'skipped':True}
        digest=drain_digests(limit=send_limit)
        self.stdout.write(
            f'Tekshirildi: {checked}; yangi hodisa: {new}; '
            f'Telegram: yuborilgan {result["sent"]}, xato {result["failed"]}; '
            f'kunlik hisobotlar: yuborilgan {digest["sent"]}, xato {digest["failed"]}; '
            f'bot sozlangan: {"yoq" if result["skipped"] else "ha"}')
