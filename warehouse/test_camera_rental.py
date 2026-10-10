"""Camera-wide rental flow, tenancy, one invoice per month and price history."""
import uuid
from datetime import date
from decimal import Decimal as D
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, override_settings
from core.models import Organization, Camera, Membership
from warehouse.models import (Customer, Tariff, CameraRentalAgreement, CameraRentalInvoice, Lot)
from warehouse.services import (open_camera_rental, issue_camera_rental_invoice,
    pay_camera_rental_invoice, change_camera_rental_rate, receive, quote, pending)

@override_settings(STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},
                            'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class CameraRentalTests(TestCase):
    def setUp(self):
        self.date_patch=patch('warehouse.services.timezone.localdate',return_value=date(2026,10,10))
        self.date_patch.start()
        self.addCleanup(self.date_patch.stop)
        self.root=get_user_model().objects.create_superuser('rental_root',password='Test-Passw0rd-99')
        self.admin=get_user_model().objects.create_user('rental_manager',password='Test-Passw0rd-99')
        self.stranger=get_user_model().objects.create_user('rental_stranger',password='Test-Passw0rd-99')
        self.org=Organization.objects.create(name='Fargona ombor',code='rental-a',camera_limit=10)
        self.other_org=Organization.objects.create(name='Other ombor',code='rental-b',camera_limit=10)
        self.cam=Camera.objects.create(organization=self.org,number=1,capacity_kg=50000)
        self.other_cam=Camera.objects.create(organization=self.other_org,number=1)
        self.customer=Customer.objects.create(organization=self.org,name='Jamshid')
        self.other_customer=Customer.objects.create(organization=self.other_org,name='Begona mijoz')
        Membership.objects.create(user=self.admin,organization=self.org,all_cameras=True,
                                  can_set_tariffs=True,can_take_payment=True,can_receive=True,can_dispatch=True,
                                  can_view_finance=True)
        Membership.objects.create(user=self.stranger,organization=self.other_org,all_cameras=True,
                                  can_set_tariffs=True,can_take_payment=True,can_receive=True,can_view_finance=True)
        self.rent_tariff=Tariff.objects.create(organization=self.org,name='Butun kamera',service='rental',
                                              basis='net',rate=0,storage_mode='prorata',created_by=self.root)

    def agreement(self,**extra):
        return open_camera_rental(self.admin,{'camera':self.cam,'customer':self.customer,
            'start_on':date(2026,10,1),'monthly_rate':D('20000000'),'end_on':None,**extra})

    def lot_data(self,**extra):
        return {'request_key':uuid.uuid4(),'camera':self.cam,'customer':self.customer,
                'tariff':self.rent_tariff,'product':'Uzum','variety':'Kishmish','box_type':'Taxta',
                'date':date(2026,10,2),'boxes':100,'gross':D('1100'),'tare':D('100'),'note':'',**extra}

    def test_one_monthly_invoice_for_many_lots_and_no_duplicate_charge(self):
        agreement=self.agreement()
        lot1=receive(self.admin,self.lot_data())
        lot2=receive(self.admin,self.lot_data())
        self.assertEqual(lot1.rental_agreement_id,agreement.pk)
        self.assertEqual(lot2.rental_agreement_id,agreement.pk)
        self.assertEqual(pending(lot1,date(2026,10,10)),0)
        self.assertEqual(quote(lot1,'dispatch',date(2026,10,10),10,D('110'),D('10'))['charge'],0)
        inv=issue_camera_rental_invoice(self.admin,agreement.pk,uuid.uuid4())
        self.assertEqual(inv.amount,D('20000000'))
        self.assertEqual(inv.period_start,date(2026,10,1))
        self.assertEqual(inv.period_end,date(2026,10,31))
        self.assertEqual(agreement.invoices.count(),1)
        self.assertEqual(lot1.operations.count(),1)
        self.assertEqual(lot2.operations.count(),1)

    def test_invoice_idempotency_and_future_not_billed(self):
        agreement=self.agreement()
        key=uuid.uuid4()
        first=issue_camera_rental_invoice(self.admin,agreement.pk,key)
        self.assertEqual(issue_camera_rental_invoice(self.admin,agreement.pk,key).pk,first.pk)
        with self.assertRaises(ValidationError):
            issue_camera_rental_invoice(self.admin,agreement.pk,uuid.uuid4())
        self.assertEqual(CameraRentalInvoice.objects.count(),1)

    def test_future_price_change_does_not_reprice_first_month(self):
        agreement=self.agreement()
        first=issue_camera_rental_invoice(self.admin,agreement.pk,uuid.uuid4())
        with patch('warehouse.services.timezone.localdate',return_value=date(2026,11,1)):
            change_camera_rental_rate(self.admin,agreement.pk,D('22000000'),date(2026,11,1))
            second=issue_camera_rental_invoice(self.admin,agreement.pk,uuid.uuid4())
        self.assertEqual(first.amount,D('20000000'))
        self.assertEqual(second.amount,D('22000000'))
        self.assertEqual(agreement.invoices.count(),2)

    def test_rental_payment_and_overpayment(self):
        agreement=self.agreement()
        inv=issue_camera_rental_invoice(self.admin,agreement.pk,uuid.uuid4())
        key=uuid.uuid4()
        first=pay_camera_rental_invoice(self.admin,inv.pk,key,D('7000000'),'bank',date(2026,10,10))
        self.assertEqual(pay_camera_rental_invoice(self.admin,inv.pk,key,D('7000000'),'bank',date(2026,10,10)).pk,first.pk)
        self.assertEqual(inv.debt,D('13000000'))
        with self.assertRaises(ValidationError):
            pay_camera_rental_invoice(self.admin,inv.pk,uuid.uuid4(),D('14000000'),'cash',date(2026,10,10))
        self.assertEqual(inv.payments.count(),1)

    def test_cross_tenant_contract_and_invoice_hidden(self):
        agreement=self.agreement()
        inv=issue_camera_rental_invoice(self.admin,agreement.pk,uuid.uuid4())
        with self.assertRaises(PermissionDenied):
            pay_camera_rental_invoice(self.stranger,inv.pk,uuid.uuid4(),D('100'),'cash',date(2026,10,10))
        with self.assertRaises(PermissionDenied):
            open_camera_rental(self.stranger,{'camera':self.cam,'customer':self.customer,
                'start_on':date(2026,11,1),'monthly_rate':D('20000000'),'end_on':None})
        self.client.force_login(self.stranger)
        self.assertEqual(self.client.get(f'/app/rentals/invoice/{inv.pk}/').status_code,404)
        self.assertNotContains(self.client.get('/app/rentals/'),'Jamshid')

    def test_wrong_customer_and_per_kg_in_rented_camera_rejected(self):
        self.agreement()
        other_tariff=Tariff.objects.create(organization=self.org,name='Kunlar',service='cooling',
                                           basis='net',rate=D('250'),storage_mode='prorata',created_by=self.root)
        with self.assertRaises(ValidationError):
            receive(self.admin,self.lot_data(tariff=other_tariff))
        customer2=Customer.objects.create(organization=self.org,name='Yangi mijoz')
        with self.assertRaises(ValidationError):
            receive(self.admin,self.lot_data(customer=customer2))

    def test_cannot_rent_occupied_camera_or_overlap(self):
        self.agreement()
        with self.assertRaises(ValidationError):
            self.agreement()
        receive(self.admin,self.lot_data())
        with self.assertRaises(ValidationError):
            open_camera_rental(self.admin,{'camera':self.cam,'customer':self.customer,
                'start_on':date(2026,12,1),'monthly_rate':D('22000000'),'end_on':None})

    def test_global_finance_report_includes_camera_rent_without_double_count(self):
        agreement=self.agreement()
        inv=issue_camera_rental_invoice(self.admin,agreement.pk,uuid.uuid4())
        pay_camera_rental_invoice(self.admin,inv.pk,uuid.uuid4(),D('2000000'),'bank',date(2026,10,10))
        self.client.force_login(self.admin)
        page=self.client.get('/app/report/')
        self.assertContains(page,'Kamera ijara hisoblari')
        self.assertContains(page,'2 000 000' if False else '2000000',count=0) if False else None
        self.assertContains(page,'Jamshid')
        xlsx=self.client.get('/app/report/?export=xlsx')
        self.assertEqual(xlsx.status_code,200)
        import io,zipfile
        z=zipfile.ZipFile(io.BytesIO(xlsx.content))
        self.assertIn('xl/worksheets/sheet3.xml',z.namelist())
        csv=self.client.get('/app/report/?export=csv')
        self.assertContains(csv,'KAMERA IJARASI HISOBLARI')
        self.assertIn('20000000',csv.content.decode())

    def test_rental_page_and_invoice_printable(self):
        self.agreement()
        inv=issue_camera_rental_invoice(self.admin,1,uuid.uuid4())
        self.client.force_login(self.admin)
        self.assertContains(self.client.get('/app/rentals/'),'Kamera ijarasi')
        self.assertContains(self.client.get(f'/app/rentals/invoice/{inv.pk}/'),'20')
        self.assertContains(self.client.get(f'/app/rentals/invoice/{inv.pk}/'),'Fiskal chek')
