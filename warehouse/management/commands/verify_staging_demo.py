"""Read-only smoke test using the actual isolated Railway STAGING PostgreSQL.

Does not modify the business data. Uses Django's request client internally,
which checks templates, forms, permissions, QR, finance and CSV on the deployed code.
This is NOT a substitute for a real phone/camera or Telegram-delivery test.
"""
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand,CommandError
from django.test import Client
from django.urls import reverse
from core import access
from core.models import Organization,Camera
from warehouse.models import (
    Lot,Operation,CameraRentalInvoice,CameraEnvironmentAlert,CameraEnvironmentReading)
from warehouse.services import totals
from warehouse.management.commands.seed_staging_demo import must_be_staging,key


class Command(BaseCommand):
    help='Real PostgreSQL smoke test: status pages, QR, invoices, exports and tenant isolation.'
    def handle(self,*args,**options):
        must_be_staging()
        User=get_user_model()
        root=User.objects.filter(is_superuser=True,is_active=True).order_by('pk').first()
        keeper=User.objects.filter(username='demo_agro_omborchi').first()
        foreign=User.objects.filter(username='demo_begona_omborchi').first()
        a=Organization.objects.filter(code='test-agrostar-holadelnik').first()
        b=Organization.objects.filter(code='test-izolyatsiya-ombor').first()
        if not (root and keeper and foreign and a and b):
            raise CommandError('TEST organizatsiyalari yoki xodimlari mavjud emas.')

        requests=0
        client=Client(HTTP_HOST='localhost')
        client.force_login(root)
        for path in (
            reverse('dashboard'),reverse('platform_dashboard'),reverse('staff_dashboard'),
            reverse('report'),reverse('rentals'),reverse('monitor_overview'),
            reverse('director_monitor'),reverse('telegram_destinations'),
            reverse('tariffs'),reverse('customers'),
        ):
            resp=client.get(path,secure=True)
            requests+=1
            if resp.status_code!=200:
                raise CommandError(f'STAGING ekranida xato: {path} -> {resp.status_code}')
        cam=Camera.objects.filter(organization=a,number=1).order_by('pk').first()
        if cam is None:raise CommandError('Demo camera yo‘q')
        lot=Lot.objects.get(create_key=key('intake:uzum250'))
        dispatch=Operation.objects.get(request_key=key('dispatch:uzum250:100'))
        invoice=CameraRentalInvoice.objects.get(request_key=key('rental-invoice:first'))
        if (lot.boxes!=150 or lot.net!=Decimal('1500') or
            dispatch.charge!=Decimal('250000') or
            totals(lot)['debt']!=Decimal('0') or invoice.debt!=Decimal('15000000')):
            raise CommandError('TEST moliyaviy yoki ombor qoldig‘i noto‘g‘ri.')

        urls=[
            (reverse('lot',args=[lot.pk]),'html'),
            (reverse('monitor_camera',args=[cam.pk]),'html'),
            (reverse('monitor_csv',args=[cam.pk]),'csv'),
            (reverse('report')+'?export=csv','csv'),
            (reverse('report')+'?export=xlsx','xlsx'),
            (reverse('qr',args=[lot.pk]),'qr'),
        ]
        for path,kind in urls:
            res=client.get(path,secure=True)
            requests+=1
            if res.status_code!=200:raise CommandError(f'STAGING hujjat xato: {kind} {res.status_code}')
            if kind=='qr' and not res.content.startswith(b'\x89PNG'):
                raise CommandError('QR fayli haqiqiy PNG emas.')
            if kind=='xlsx' and not res.content.startswith(b'PK'):
                raise CommandError('XLSX fayli xato.')
        # A scoped omborchi cannot see another tenant's QR or finance.
        alien=Lot.objects.get(create_key=key('intake:other'))
        client.force_login(keeper)
        if access.cameras(keeper).filter(organization=b).exists():
            raise CommandError('Tenant isolation failure: keeper sees foreign cameras.')
        resp=client.get(reverse('lot',args=[alien.pk]),secure=True);requests+=1
        if resp.status_code not in (403,404):
            raise CommandError('Tenant isolation failure: keeper sees foreign lot.')
        client.force_login(foreign)
        resp=client.get(reverse('lot',args=[lot.pk]),secure=True);requests+=1
        if resp.status_code not in (403,404):
            raise CommandError('Tenant isolation failure: other company sees main lot.')
        # Any Telegram alert is local/draft until a chat ID is configured.
        warnings=CameraEnvironmentAlert.objects.filter(
            camera__organization=a,resolved_at__isnull=True).count()
        self.stdout.write(
            f'STAGING SMOKE OK: HTTP checks {requests}; '
            f'organizations {Organization.objects.count()}; cameras {Camera.objects.count()}; '
            f'lots {Lot.objects.count()}; active sample alerts {warnings}; '
            f'dispatch balance {lot.boxes} boxes; rental debt {invoice.debt}.')
