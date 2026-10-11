"""One-time staging PostgreSQL verification against existing TEST records.

No changes to lots, invoices, payments, price plans, alerts, or Telegram routes.
Creates only Django's short-lived test-client authentication session.
"""
import csv
import io
import zipfile
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand,CommandError
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from warehouse.management.commands.seed_staging_demo import must_be_staging,key
from core.models import Organization,Camera
from warehouse.models import (
 Lot,Operation,CameraRentalInvoice,CameraRentalPayment,DailyTelegramDigest,
 TelegramAlertDestination
)
from warehouse.services import totals
from django.db.models import Sum,Count


class Command(BaseCommand):
    help='Verify real isolated staging TEST business snapshot, QR PNG, CSV/XLSX, and tenant isolation.'
    def handle(self,*args,**options):
        must_be_staging()
        User=get_user_model()
        root=User.objects.filter(is_superuser=True,is_active=True).order_by('pk').first()
        keeper=User.objects.filter(username='demo_begona_omborchi').first()
        org=Organization.objects.filter(code='test-agrostar-holadelnik').first()
        other=Organization.objects.filter(code='test-izolyatsiya-ombor').first()
        if not all((root,keeper,org,other)):
            raise CommandError('TEST tashkilot yoki hisoblar yetishmaydi')
        lot=Lot.objects.filter(create_key=key('intake:uzum250')).select_related('camera').first()
        op=Operation.objects.filter(request_key=key('dispatch:uzum250:100')).first()
        invoice=CameraRentalInvoice.objects.filter(request_key=key('rental-invoice:first')).first()
        if not all((lot,op,invoice)):
            raise CommandError('TEST operatsiyalari mavjud emas')
        if (lot.organization_id!=org.pk or op.lot_id!=lot.pk or
            lot.initial_boxes!=250 or lot.boxes!=150 or
            lot.initial_gross!=Decimal('2750') or lot.gross!=Decimal('1650') or
            lot.net!=Decimal('1500') or
            op.boxes!=100 or op.net!=Decimal('1000') or
            op.charge!=Decimal('250000') or op.payment!=Decimal('250000') or
            totals(lot)['debt']!=0):
            raise CommandError('Kirim, chiqim yoki xizmat haqi qoldiqlari mos emas')
        if (invoice.agreement.camera.organization_id!=org.pk or
            invoice.amount!=Decimal('20000000') or
            invoice.paid!=Decimal('5000000') or
            invoice.debt!=Decimal('15000000') or
            CameraRentalPayment.objects.filter(invoice=invoice).count()!=1):
            raise CommandError('Oylik ijara/to‘lov/qarz qoldiqlari mos emas')
        stock=Lot.objects.filter(organization=org,closed_on__isnull=True).aggregate(
            count=Count('pk'),boxes=Sum('boxes'),gross=Sum('gross'),tare=Sum('tare'))
        if (stock['count']!=6 or stock['boxes']!=550 or
            stock['gross']-stock['tare']!=Decimal('5510')):
            raise CommandError('Faol ombor qoldig‘i 08:00 hisobotiga mos emas')

        test=Client(HTTP_HOST='localhost')
        test.force_login(root)
        checks=0
        routes=[
           reverse('scanner'),reverse('dashboard'),reverse('platform_dashboard'),
           reverse('lot',args=[lot.pk]),reverse('qr',args=[lot.pk]),
           reverse('label',args=[lot.pk]),reverse('receipt',args=[op.pk]),
           reverse('operation',args=[lot.pk,'dispatch']),
           reverse('report'),reverse('report')+'?export=csv',
           reverse('report')+'?export=xlsx',
           reverse('customer_csv'),
           reverse('customer_excel')+'?customer='+str(lot.customer_id),
           reverse('rental_invoice',args=[invoice.pk]),
           reverse('monitor_camera',args=[lot.camera_id]),
        ]
        for path in routes:
            response=test.get(path,secure=True)
            checks+=1
            if response.status_code!=200:
                raise CommandError(f'STAGING HTTP ishlamadi {path}: {response.status_code}')
            if path==reverse('qr',args=[lot.pk]) and not response.content.startswith(b'\x89PNG'):
                raise CommandError('QR PNG noto‘g‘ri')
            if 'export=xlsx' in path or 'customer.xlsx' in path:
                if not response.content.startswith(b'PK'):
                    raise CommandError('Excel fayli noto‘g‘ri')
                with zipfile.ZipFile(io.BytesIO(response.content)) as book:
                    if book.testzip() is not None or 'xl/workbook.xml' not in book.namelist():
                        raise CommandError('Excel ZIP ichki tuzilishi yaroqsiz')
            if 'export=csv' in path:
                raw=response.content.decode('utf-8')
                if raw.count('\ufeff')!=1:
                    raise CommandError('CSV kodlash nuqsoni: BOM bir martadan ko‘p yozilgan')
                text=raw.lstrip('\ufeff')
                csv_rows=list(csv.reader(io.StringIO(text)))
                if not csv_rows or 'Kamera ijara hisobi' not in csv_rows[0]:
                    raise CommandError('CSV ustunlari noto‘g‘ri')
                if not all(s in text for s in ('20000000.00','5000000.00','15000000.00')):
                    raise CommandError('CSVdagi ijara/to‘lov/qarz raqamlari xato')

        # Isolation: foreign staff gets no customer/QR/receipt/money data.
        test.force_login(keeper)
        for path in [reverse('lot',args=[lot.pk]),reverse('qr',args=[lot.pk]),
                     reverse('receipt',args=[op.pk]),
                     reverse('operation',args=[lot.pk,'dispatch'])]:
            res=test.get(path,secure=True)
            checks+=1
            if res.status_code not in (403,404):
                raise CommandError(f'Begona xodimda ruxsatlar buzilgan: {path}')
        res=test.get(reverse('report')+'?export=csv',secure=True)
        checks+=1
        if res.status_code not in (403,404):
            raise CommandError('Begona xodim moliyaviy hisobotni o‘qiy oldi')
        route=TelegramAlertDestination.objects.filter(
            organization=org,enabled=True,chat_id='-1004316868592').first()
        if route is None:raise CommandError('Telegram sinov manzili mos emas')
        delivered=DailyTelegramDigest.objects.filter(
            organization=org,report_date=timezone.localdate(),
            slot_hour=8,delivery_status='sent',chat_id=route.chat_id,
            sent_at__isnull=False).count()
        # Printed explicitly: the 14:00 and 20:00 entries are NOT inferred.
        today=timezone.localdate()
        slots={hr:list(DailyTelegramDigest.objects.filter(
            organization=org,report_date=today,slot_hour=hr
        ).values_list('delivery_status',flat=True)) for hr in (8,14,20)}
        if delivered!=1:
            raise CommandError('08:00 real Telegram DB status sent emas')
        self.stdout.write(
            'STAGING RELEASE SNAPSHOT OK: '
            f'http={checks}; orgs={Organization.objects.count()}; '
            f'parties={Lot.objects.count()}; '
            f'active_boxes={stock["boxes"]}; active_net_kg={stock["gross"]-stock["tare"]}; '
            f'dispatch_boxes={op.boxes}; dispatch_fee_uzs={op.charge}; '
            f'rent_due_uzs={invoice.debt}; '
            f'digests_08_14_20={slots}; production_untouched=true'
        )
