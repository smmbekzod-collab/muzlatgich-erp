"""Release-candidate acceptance tests; isolated Django TEST database only.

HTTP QR / two-step dispatch / idempotent money / rental totals / tenant isolation.
The real Railway STAGING smoke is the separate verify_staging_demo command.
"""
import csv
import io
import uuid
import zipfile
from decimal import Decimal
from unittest.mock import patch
import qrcode
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import Organization, Camera
from warehouse.models import (
    Lot, Operation, Tariff, Customer, CameraRentalInvoice,CameraRentalPayment,
)
from warehouse.services import totals, act, quote, pending
from warehouse.management.commands.seed_staging_demo import key


def _is_decimal_equal(raw, expected):
    try:return Decimal(raw)==Decimal(expected)
    except (ValueError,ArithmeticError):return False


STAGING_TEST_ENV={
    'ALLOW_STAGING_DEMO_SEED':'1',
    'RAILWAY_ENVIRONMENT_ID':'79dae0a2-be02-4dc2-ac16-3675ffc1aa62',
    'ALLOW_SEED_SQLITE_TESTS':'1',
}


@override_settings(
    DEBUG=True,ALLOWED_HOSTS=['localhost','testserver','staging.example.test'],
    STORAGES={
        'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},
        'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'},
    })
class QrAndFinanceAcceptanceTests(TestCase):
    def setUp(self):
        self.env_patch=patch.dict('os.environ',STAGING_TEST_ENV)
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        self.root=get_user_model().objects.create_superuser(
            username='release_owner',password='Test-Only-Strong-Password!321')
        call_command('seed_staging_demo','--apply',stdout=io.StringIO(),verbosity=0)
        self.org=Organization.objects.get(code='test-agrostar-holadelnik')
        self.other=Organization.objects.get(code='test-izolyatsiya-ombor')
        self.base=Lot.objects.get(create_key=key('intake:uzum250'))
        self.new_lot=Lot.objects.get(create_key=key('intake:uzum60'))
        self.alien=Lot.objects.get(create_key=key('intake:other'))
        self.invoice=CameraRentalInvoice.objects.get(request_key=key('rental-invoice:first'))
        self.client.force_login(self.root)

    def test_qr_png_uses_correct_scoped_lot_absolute_url(self):
        with patch('warehouse.views.qrcode.make',wraps=qrcode.make) as make:
            response=self.client.get(reverse('qr',args=[self.base.pk]),
                secure=True,HTTP_HOST='staging.example.test')
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.content.startswith(b'\x89PNG\r\n\x1a\n'))
        self.assertIn('image/png',response['Content-Type'])
        self.assertIn('private',response['Cache-Control'])
        self.assertIn('no-store',response['Cache-Control'])
        make.assert_called_once_with(
            'https://staging.example.test'+reverse('lot',args=[self.base.pk]))
        scan=self.client.get(reverse('scanner'))
        self.assertContains(scan,'warehouse/vendor/html5-qrcode.min.js')
        self.assertContains(scan,'manual-open')
        self.assertContains(scan,'/app/lot/')
        self.assertContains(scan,'<details class="scanner-permission-help" id="scanner-help">',html=False)
        self.assertContains(scan,'<summary>Skaner ishlamasa',html=False)
        self.assertNotContains(scan,'<details class="scanner-permission-help" id="scanner-help" open')
        self.assertContains(scan,'Заблокировано автоматически')
        self.assertContains(scan,'Запрещено')
        self.assertContains(scan,'muzlatgich-erp-v2-web-staging.up.railway.app')
        self.assertContains(scan,'Reset permissions')
        self.assertContains(scan,'id="copy-scanner-url"')
        self.assertContains(scan,'id="scanner-url-fallback"')
        self.assertContains(scan,'Request Camera Permissions')

    def test_http_intake_then_dispatch_preview_confirmation_and_receipt(self):
        today=timezone.localdate()
        cam=Camera.objects.filter(organization=self.org,number=1).first()
        cust=Customer.objects.get(organization=self.org,name__contains='MIJOZ 01')
        rate=Tariff.objects.get(organization=self.org,service='tiered',is_active=True)
        new_key=uuid.uuid4()
        response=self.client.post(reverse('intake'),{
            'request_key':str(new_key),'date':today.isoformat(),'camera':str(cam.pk),
            'customer':str(cust.pk),'tariff':str(rate.pk),
            'product':'TEST Acceptance','variety':'Kishmish','box_type':'Yogoch',
            'boxes':'250','gross':'2750','tare':'250','note':'TEST / E2E',
        })
        self.assertEqual(response.status_code,302)
        lot=Lot.objects.get(create_key=new_key)
        self.assertEqual((lot.boxes,lot.net),(250,Decimal('2500')))
        self.assertEqual(lot.operations.filter(kind='receive').count(),1)

        dispatch_key=uuid.uuid4()
        data={
            'request_key':str(dispatch_key),'date':today.isoformat(),
            'boxes':'100','gross':'1100','tare':'100',
            'payment':'250000','payment_method':'cash','note':'TEST partial dispatch',
        }
        url=reverse('operation',args=[lot.pk,'dispatch'])
        preview=self.client.post(url,{**data,'preview':'yes'})
        self.assertEqual(preview.status_code,200)
        self.assertEqual(preview.context['preview']['charge'],Decimal('250000'))
        self.assertEqual(preview.context['preview']['boxes_after'],150)
        token=preview.context['preview_token']
        self.assertTrue(token)
        confirm=self.client.post(url,{**data,'confirm':'yes','preview_token':token})
        self.assertEqual(confirm.status_code,302)
        operation=Operation.objects.get(request_key=dispatch_key)
        self.assertEqual(operation.kind,'dispatch')
        self.assertEqual((operation.charge,operation.payment),
                         (Decimal('250000'),Decimal('250000')))
        lot.refresh_from_db()
        self.assertEqual((lot.boxes,lot.net),(150,Decimal('1500')))
        self.assertEqual(totals(lot)['debt'],0)
        self.assertEqual(totals(lot)['paid'],Decimal('250000'))
        self.assertEqual(self.client.get(reverse('receipt',args=[operation.pk])).status_code,200)
        self.assertEqual(self.client.get(reverse('qr',args=[lot.pk])).status_code,200)
        again=act(self.root,lot.pk,'dispatch',{
            'request_key':dispatch_key,'date':today,'boxes':100,
            'gross':Decimal('1100'),'tare':Decimal('100'),
            'payment':Decimal('250000'),'payment_method':'cash'})
        self.assertEqual(again.pk,operation.pk)
        lot.refresh_from_db()
        self.assertEqual(lot.boxes,150)
        self.assertEqual(lot.operations.filter(kind='dispatch').count(),1)

    def test_tampered_dispatch_confirmation_writes_nothing(self):
        url=reverse('operation',args=[self.new_lot.pk,'dispatch'])
        day=timezone.localdate()
        data={
            'request_key':str(uuid.uuid4()),'date':day.isoformat(),
            'boxes':'10','gross':'120','tare':'10',
            'payment':'33000','payment_method':'cash','note':'TEST',
        }
        response=self.client.post(url,{**data,'preview':'yes'})
        self.assertEqual(response.status_code,200)
        token=response.context['preview_token']
        prior=Operation.objects.filter(lot=self.new_lot).count()
        invalid=self.client.post(url,{
            **data,'gross':'121','confirm':'yes','preview_token':token})
        self.assertEqual(invalid.status_code,200)
        self.assertContains(invalid,'Maydonlar o‘zgargan')
        self.new_lot.refresh_from_db()
        self.assertEqual(self.new_lot.boxes,60)
        self.assertEqual(Operation.objects.filter(lot=self.new_lot).count(),prior)

    def test_existing_demo_qr_finance_and_rental_balances(self):
        self.assertEqual((self.base.initial_boxes,self.base.boxes),(250,150))
        self.assertEqual((self.base.initial_gross,self.base.gross),
                         (Decimal('2750'),Decimal('1650')))
        self.assertEqual(self.base.net,Decimal('1500'))
        op=Operation.objects.get(request_key=key('dispatch:uzum250:100'))
        self.assertEqual((op.boxes,op.net,op.charge,op.payment),
            (100,Decimal('1000'),Decimal('250000'),Decimal('250000')))
        self.assertEqual(totals(self.base)['debt'],0)
        self.assertEqual(self.invoice.amount,Decimal('20000000'))
        self.assertEqual(self.invoice.paid,Decimal('5000000'))
        self.assertEqual(self.invoice.debt,Decimal('15000000'))
        self.assertEqual(CameraRentalPayment.objects.filter(invoice=self.invoice).count(),1)
        self.assertEqual(self.client.get(
            reverse('rental_invoice',args=[self.invoice.pk])).status_code,200)

    def test_csv_and_xlsx_balance_correct_and_files_valid(self):
        csv_response=self.client.get(reverse('report')+'?export=csv')
        self.assertEqual(csv_response.status_code,200)
        lines=list(csv.reader(io.StringIO(csv_response.content.decode('utf-8-sig'))))
        self.assertIn('Kamera ijara hisobi',lines[0])
        self.assertIn('Jami tushum',lines[0])
        raw=csv_response.content.decode('utf-8')
        self.assertEqual(raw.count('\ufeff'),1,'CSV should contain exactly one UTF-8 BOM')
        text='\n'.join(','.join(row) for row in lines)
        self.assertIn('TEST — Agro Star Muzlatkich ERP',text)
        # Compare numbers as Decimal: some legitimate values are rendered without .00
        def contains_number(amount):
            return any(any(
                cell.strip() and _is_decimal_equal(cell.strip(),amount)
                for cell in row) for row in lines)
        for amount in ['20000000','5000000','15000000','250000']:
            self.assertTrue(contains_number(amount),f'Missing amount: {amount}')
        self.assertIn('TEST — Agro Star Muzlatkich ERP',text)
        excel=self.client.get(reverse('report')+'?export=xlsx')
        self.assertEqual(excel.status_code,200)
        self.assertTrue(excel.content.startswith(b'PK'))
        with zipfile.ZipFile(io.BytesIO(excel.content)) as book:
            self.assertIsNone(book.testzip())
            self.assertIn('xl/workbook.xml',book.namelist())
        client_csv=self.client.get(reverse('customer_csv'))
        self.assertEqual(client_csv.status_code,200)
        self.assertIn('250000.00',client_csv.content.decode('utf-8-sig'))
        client_excel=self.client.get(reverse('customer_excel')+
                                     '?customer='+str(self.base.customer_id))
        self.assertEqual(client_excel.status_code,200)
        self.assertTrue(client_excel.content.startswith(b'PK'))

    def test_scoped_employee_cannot_view_foreign_qr_receipt_or_finance(self):
        employee=get_user_model().objects.get(username='demo_begona_omborchi')
        self.client.force_login(employee)
        for url in [reverse('lot',args=[self.base.pk]),
                    reverse('qr',args=[self.base.pk]),
                    reverse('operation',args=[self.base.pk,'dispatch']),
                    reverse('receipt',args=[Operation.objects.get(
                        request_key=key('dispatch:uzum250:100')).pk])]:
            with self.subTest(url=url):
                response=self.client.get(url)
                self.assertIn(response.status_code,(403,404))
        denied=self.client.get(reverse('report')+'?export=csv')
        self.assertIn(denied.status_code,(403,404))
        own=self.client.get(reverse('lot',args=[self.alien.pk]))
        self.assertEqual(own.status_code,200)
        qr=self.client.get(reverse('qr',args=[self.alien.pk]))
        self.assertEqual(qr.status_code,200)


    def test_daily_digest_separates_rental_invoice_and_per_kg_charge(self):
        from warehouse.daily_digests import compose_organization_report
        report=compose_organization_report(
            self.org,timezone.localdate(),8,now=timezone.now())
        self.assertIn('Davrda yuk bo‘yicha xizmat haqi: 250 000 so‘m',report)
        self.assertIn('Davrda chiqarilgan kamera ijarasi hisobi: 20 000 000 so‘m',report)
        self.assertIn('Davrda jami hisoblangan: 20 250 000 so‘m',report)
        self.assertIn('Davrda olingan to‘lov: 5 250 000 so‘m',report)
        self.assertIn('Kamera ijarasi bo‘yicha qarz: 15 000 000 so‘m',report)

    def test_customer_filter_export_does_not_leak_other_tenant(self):
        accountant=get_user_model().objects.get(username='demo_agro_buxgalter')
        self.client.force_login(accountant)
        response=self.client.get(reverse('customer_csv')+'?customer='+
            str(self.alien.customer_id))
        self.assertEqual(response.status_code,200)
        text=response.content.decode('utf-8-sig')
        self.assertNotIn('TEST — Izolyatsiya Tashkiloti',text)
        self.assertNotIn('TEST MIJOZ — Begona',text)
        self.assertNotIn('TEST — Agro Star Muzlatkich ERP',text)
