import uuid
from decimal import Decimal as D
from datetime import date,timedelta
from unittest.mock import patch
from html.parser import HTMLParser
from django.test import TestCase,override_settings,Client
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied,ValidationError
from core.models import Organization,Camera,Membership
from .models import Customer,Tariff,Lot,Operation,Expense
from .services import receive,act,quote,totals,pending,storage_total

@override_settings(STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class WorkflowTests(TestCase):
    def setUp(self):
        self.timepatch=patch('warehouse.services.timezone.localdate',return_value=date(2026,10,7));self.timepatch.start();self.addCleanup(self.timepatch.stop)
        self.root=get_user_model().objects.create_superuser('root',password='Long-Test-Password!')
        self.u=get_user_model().objects.create_user('keeper',password='Long-Test-Password!',is_staff=True)
        self.a=Organization.objects.create(name='Agro A',code='a',camera_limit=10)
        self.b=Organization.objects.create(name='Agro B',code='b',camera_limit=20)
        self.c1=Camera.objects.create(organization=self.a,number=1)
        self.c2=Camera.objects.create(organization=self.a,number=2)
        self.cb=Camera.objects.create(organization=self.b,number=1)
        self.m=Membership.objects.create(user=self.u,organization=self.a,all_cameras=True,can_receive=True,can_dispatch=True,can_take_payment=True,can_view_finance=True,can_transfer=True,can_set_tariffs=True,can_manage_expenses=True)
        self.customer=Customer.objects.create(organization=self.a,name='Aliyev',phone='998900000000')
        self.tariff=Tariff.objects.create(organization=self.a,name='300 sof',service='cooling',basis='net',rate=300,storage_mode='prorata',created_by=self.root)
        self.lot=receive(self.u,self.intake_data())
        self.client.force_login(self.u)
    def intake_data(self,**extra):
        return {'request_key':uuid.uuid4(),'camera':self.c1,'customer':self.customer,'tariff':self.tariff,'product':'Uzum','variety':'Kishmish','box_type':'Taxta','date':date(2026,10,1),'boxes':250,'gross':D('2750'),'tare':D('250'),'note':'',**extra}
    def out(self,**extra):
        return {'request_key':uuid.uuid4(),'date':date(2026,10,6),'boxes':100,'gross':D('1100'),'tare':D('100'),'payment':D('1500000'),'payment_method':'cash','note':'',**extra}
    def test_partial_dispatch_and_receipt(self):
        op=act(self.u,self.lot.pk,'dispatch',self.out())
        self.assertEqual(op.charge,D('1500000'));self.lot.refresh_from_db()
        self.assertEqual(self.lot.boxes,150);self.assertEqual(self.lot.net,D('1500'));self.assertEqual(totals(self.lot)['debt'],0)
        self.assertContains(self.client.get(f'/app/receipt/{op.pk}/'),'150')
    def test_full_close_does_not_double_bill(self):
        act(self.u,self.lot.pk,'dispatch',self.out())
        second=act(self.u,self.lot.pk,'dispatch',self.out(date=date(2026,10,7),boxes=150,gross=D('1650'),tare=D('150'),payment=D('2700000')))
        self.lot.refresh_from_db();self.assertEqual(second.charge,D('2700000'));self.assertEqual(self.lot.boxes,0)
        self.assertEqual(totals(self.lot)['charged'],D('4200000'));self.assertEqual(pending(self.lot),0)
    def test_duplicate_submit_once(self):
        data=self.out();first=act(self.u,self.lot.pk,'dispatch',data);second=act(self.u,self.lot.pk,'dispatch',data)
        self.assertEqual(first.pk,second.pk);self.lot.refresh_from_db();self.assertEqual(self.lot.boxes,150)
    def test_over_dispatch_rejected(self):
        with self.assertRaises(ValidationError):act(self.u,self.lot.pk,'dispatch',self.out(boxes=251))
        self.lot.refresh_from_db();self.assertEqual(self.lot.boxes,250)
    def test_tare_and_net_overdraw_rejected(self):
        with self.assertRaises(ValidationError):act(self.u,self.lot.pk,'dispatch',self.out(tare=D('251')))
    def test_last_boxes_need_all_weight(self):
        with self.assertRaises(ValidationError):act(self.u,self.lot.pk,'dispatch',self.out(boxes=250))
    def test_same_day_zero_and_inclusive_day(self):
        self.assertEqual(quote(self.lot,'dispatch',date(2026,10,1),100,D('1100'),D('100'))['charge'],0)
        self.lot.bill_exit_day=True;self.lot.save()
        self.assertEqual(quote(self.lot,'dispatch',date(2026,10,1),100,D('1100'),D('100'))['charge'],300000)
    def test_gross_tariff_500(self):
        self.lot.basis='gross';self.lot.rate=D('500');self.lot.save()
        self.assertEqual(quote(self.lot,'dispatch',date(2026,10,6),100,D('1100'),D('100'))['charge'],D('2750000'))
    def test_advance_used(self):
        act(self.u,self.lot.pk,'payment',self.out(date=date(2026,10,2),payment=D('500000')))
        self.assertEqual(quote(self.lot,'dispatch',date(2026,10,6),100,D('1100'),D('100'))['due'],D('1000000'))
        act(self.u,self.lot.pk,'dispatch',self.out(payment=D('1000000')))
        self.assertEqual(totals(self.lot)['debt'],0)
    def test_debt_permission_required(self):
        with self.assertRaises(PermissionDenied):act(self.u,self.lot.pk,'dispatch',self.out(payment=0))
        self.assertEqual(self.lot.operations.count(),1)
    def test_debt_permission_works(self):
        self.m.can_dispatch_on_debt=True;self.m.save()
        act(self.u,self.lot.pk,'dispatch',self.out(payment=0));self.assertEqual(totals(self.lot)['debt'],1500000)
    def test_cash_permission_required(self):
        self.m.can_take_payment=False;self.m.save()
        with self.assertRaises(PermissionDenied):act(self.u,self.lot.pk,'dispatch',self.out())
    def test_tariff_changes_do_not_rewrite_lot(self):
        self.tariff.rate=500;self.tariff.save();self.lot.refresh_from_db()
        self.assertEqual(self.lot.rate,300)
    def test_storage_prorata_and_idempotent_billing(self):
        self.lot.service='storage';self.lot.rate=D('20000000');self.lot.save()
        data=self.out(date=date(2026,10,7),payment=0)
        first=act(self.u,self.lot.pk,'storage_bill',data)
        second=act(self.u,self.lot.pk,'storage_bill',self.out(date=date(2026,10,7),payment=0))
        self.assertEqual(first.charge,D('4516129'));self.assertEqual(second.charge,0)
        self.lot.refresh_from_db();self.assertEqual(pending(self.lot,date(2026,10,7)),0)
    def test_storage_partial_does_not_reduce_fixed_fee(self):
        self.lot.service='storage';self.lot.rate=D('20000000');self.lot.storage_mode='full';self.lot.save()
        first=act(self.u,self.lot.pk,'dispatch',self.out(payment=D('20000000')))
        second=act(self.u,self.lot.pk,'dispatch',self.out(boxes=50,gross=D('550'),tare=D('50'),payment=0))
        self.assertEqual(first.charge,D('20000000'));self.assertEqual(second.charge,0)
    def test_anniversary_month_leap_boundaries(self):
        self.lot.service='storage';self.lot.rate=D('3100');self.lot.received_on=date(2024,1,31)
        self.assertEqual(storage_total(self.lot,date(2024,2,28)),D('3100'))
        self.assertEqual(storage_total(self.lot,date(2024,3,30)),D('6200'))
    def test_future_date_rejected(self):
        with self.assertRaises(ValidationError):act(self.u,self.lot.pk,'dispatch',self.out(date=date(2027,1,1)))
    def test_backdated_after_stock_movement_rejected(self):
        act(self.u,self.lot.pk,'dispatch',self.out())
        with self.assertRaises(ValidationError):act(self.u,self.lot.pk,'dispatch',self.out(date=date(2026,10,5)))
    def test_loss_without_box_loss(self):
        op=act(self.u,self.lot.pk,'loss',self.out(boxes=0,gross=D('10'),tare=D('0'),payment=0))
        self.lot.refresh_from_db();self.assertEqual(self.lot.boxes,250);self.assertEqual(self.lot.net,2490);self.assertEqual(op.charge,15000)
    def test_transfer_preserves_qr_and_billing(self):
        op=act(self.u,self.lot.pk,'transfer',self.out(target_camera=self.c2))
        self.lot.refresh_from_db();self.assertEqual(self.lot.camera,self.c2);self.assertEqual(self.lot.boxes,250);self.assertEqual(op.charge,0)
        self.assertEqual(quote(self.lot,'dispatch',date(2026,10,6),100,D('1100'),D('100'))['charge'],1500000)
    def test_cross_org_transfer_denied(self):
        with self.assertRaises(PermissionDenied):act(self.u,self.lot.pk,'transfer',self.out(target_camera=self.cb))
    def test_capacity_limit(self):
        self.c2.capacity_kg=D('1000');self.c2.save()
        with self.assertRaises(ValidationError):act(self.u,self.lot.pk,'transfer',self.out(target_camera=self.c2))
    def test_occupied_camera_cannot_deactivate(self):
        self.c1.is_active=False
        with self.assertRaises(ValidationError):self.c1.save()
    def test_qr_requires_login_and_is_png(self):
        response=self.client.get(f'/app/lot/{self.lot.pk}/qr.png')
        self.assertEqual(response.status_code,200);self.assertTrue(response.content.startswith(b'\x89PNG'))
        self.client.logout();self.assertEqual(self.client.get(f'/app/lot/{self.lot.pk}/qr.png').status_code,302)
    def test_cross_tenant_qr_does_not_disclose(self):
        foreign=get_user_model().objects.create_user('foreign',is_staff=True)
        Membership.objects.create(user=foreign,organization=self.b,all_cameras=True)
        self.client.force_login(foreign)
        self.assertEqual(self.client.get(f'/app/lot/{self.lot.pk}/').status_code,404)
        self.assertEqual(self.client.get(f'/app/lot/{self.lot.pk}/qr.png').status_code,404)
    def test_all_pages_render(self):
        for path in ['/app/','/app/receive/','/app/customers/','/app/tariffs/','/app/expenses/','/app/report/','/app/scan/',f'/app/lot/{self.lot.pk}/',f'/app/lot/{self.lot.pk}/dispatch/',f'/app/lot/{self.lot.pk}/label/','/manifest.json','/sw.js']:
            with self.subTest(path=path):self.assertEqual(self.client.get(path).status_code,200)
    def test_confirm_flow_http(self):
        d=self.out();d['date']=d['date'].isoformat();d['request_key']=str(d['request_key'])
        url=f'/app/lot/{self.lot.pk}/dispatch/'
        response=self.client.post(url,d)
        self.assertContains(response,'Hisobni tekshiring')
        self.lot.refresh_from_db();self.assertEqual(self.lot.boxes,250)
        import re, html
        token=html.unescape(re.search(r'name="preview_token" value="([^"]+)"', response.content.decode()).group(1))
        d['preview_token']=token
        d['confirm']='yes';response=self.client.post(url,d)
        self.assertEqual(response.status_code,302);self.lot.refresh_from_db();self.assertEqual(self.lot.boxes,150)
    def test_csrf_is_required(self):
        client=Client(enforce_csrf_checks=True);client.force_login(self.u)
        self.assertEqual(client.post(f'/app/lot/{self.lot.pk}/payment/',{}).status_code,403)
    def test_csv_exports(self):
        response=self.client.get('/app/report/?export=csv');self.assertEqual(response.status_code,200);self.assertIn('text/csv',response['Content-Type'])
    def test_finance_permission(self):
        self.m.can_view_finance=False;self.m.save();self.assertEqual(self.client.get('/app/report/').status_code,403)
    def test_no_duplicate_receive(self):
        data=self.intake_data();a=receive(self.u,data);b=receive(self.u,data);self.assertEqual(a.pk,b.pk)
    def test_reversal_restores_stock_and_money_once(self):
        from .services import reverse_last
        op=act(self.u,self.lot.pk,'dispatch',self.out());key=uuid.uuid4()
        reversal=reverse_last(self.root,op.pk,key,'Xato miqdor')
        self.assertEqual(reverse_last(self.root,op.pk,key,'Xato miqdor').pk,reversal.pk)
        self.lot.refresh_from_db();self.assertEqual(self.lot.boxes,250)
        self.assertEqual(totals(self.lot)['charged'],0);self.assertEqual(totals(self.lot)['paid'],0)
    def test_reversal_rejects_staff_and_old_documents(self):
        from .services import reverse_last
        op=act(self.u,self.lot.pk,'dispatch',self.out())
        with self.assertRaises(PermissionDenied):reverse_last(self.u,op.pk,uuid.uuid4(),'Xato')
        act(self.u,self.lot.pk,'payment',self.out(payment=D('1')))
        with self.assertRaises(ValidationError):reverse_last(self.root,op.pk,uuid.uuid4(),'Xato')
    def test_storage_reversal_restores_accrual(self):
        from .services import reverse_last
        self.lot.service='storage';self.lot.rate=D('20000000');self.lot.save()
        op=act(self.u,self.lot.pk,'storage_bill',self.out(payment=0))
        reverse_last(self.root,op.pk,uuid.uuid4(),'Xato')
        self.lot.refresh_from_db();self.assertEqual(self.lot.storage_billed,0)
        self.assertGreater(pending(self.lot),0)
    def test_transfer_reversal(self):
        from .services import reverse_last
        op=act(self.u,self.lot.pk,'transfer',self.out(target_camera=self.c2))
        reverse_last(self.root,op.pk,uuid.uuid4(),'Xato')
        self.lot.refresh_from_db();self.assertEqual(self.lot.camera,self.c1)

    def _dispatch_preview(self, data=None):
        import re, html
        d=data or self.out()
        d={**d, 'date':d['date'].isoformat(), 'request_key':str(d['request_key'])}
        response=self.client.post(f'/app/lot/{self.lot.pk}/dispatch/', d)
        self.assertEqual(response.status_code,200)
        match=re.search(r'name="preview_token" value="([^"]+)"',response.content.decode())
        self.assertIsNotNone(match)
        d['preview_token']=html.unescape(match.group(1))
        return d

    def test_dispatch_rejects_direct_confirmation_without_preview(self):
        d=self.out()
        d.update({'date':d['date'].isoformat(),'request_key':str(d['request_key']),'confirm':'yes'})
        response=self.client.post(f'/app/lot/{self.lot.pk}/dispatch/',d)
        self.assertContains(response,'Avval xizmat haqini hisoblab')
        self.assertEqual(self.lot.operations.count(),1)

    def test_dispatch_rejects_changed_inputs_after_preview(self):
        d=self._dispatch_preview()
        d['boxes']=80
        d['confirm']='yes'
        response=self.client.post(f'/app/lot/{self.lot.pk}/dispatch/',d)
        self.assertContains(response,'Maydonlar o‘zgargan')
        self.assertEqual(self.lot.operations.count(),1)

    def test_dispatch_rejects_stale_preview_after_other_dispatch(self):
        d=self._dispatch_preview()
        # Another authorized checkout changes the lot, although the form itself is unchanged.
        act(self.u,self.lot.pk,'dispatch',self.out())
        d['confirm']='yes'
        response=self.client.post(f'/app/lot/{self.lot.pk}/dispatch/',d)
        self.assertContains(response,'qoldig‘i yoki hisob holati o‘zgargan')
        self.assertEqual(self.lot.operations.filter(kind='dispatch').count(),1)

    def test_dispatch_rejects_preview_from_different_user(self):
        d=self._dispatch_preview()
        other=get_user_model().objects.create_user('second_keeper',password='Long-Test-Password!',is_staff=True)
        Membership.objects.create(user=other,organization=self.a,all_cameras=True,can_dispatch=True,can_take_payment=True)
        self.client.force_login(other)
        d['confirm']='yes'
        response=self.client.post(f'/app/lot/{self.lot.pk}/dispatch/',d)
        self.assertContains(response,'Tasdiqlash muddati tugagan yoki ma’lumot o‘zgargan' if False else 'Maydonlar o‘zgargan')
        self.assertEqual(self.lot.operations.count(),1)

    def test_scan_and_dispatch_mobile_controls_render(self):
        scan=self.client.get('/app/scan/')
        self.assertContains(scan,'manual-open')
        r=self.client.get(f'/app/lot/{self.lot.pk}/dispatch/')
        self.assertContains(r,'data-fill-all')
        self.assertContains(r,'data-dispatch-form')
        self.assertContains(r,'Hisobni ko‘rish')

    def test_tiered_tariff_boundaries_and_total_price(self):
        self.tariff.service='tiered'
        self.tariff.tier_1_10=D('250')
        self.tariff.tier_11_15=D('300')
        self.tariff.tier_16_25=D('400')
        self.tariff.tier_26_30=D('450')
        self.tariff.tier_31_plus=D('450')
        self.tariff.save()
        lot=receive(self.u,self.intake_data(tariff=self.tariff))
        for age,rate in [(1,250),(10,250),(11,300),(15,300),(16,400),
                         (25,400),(26,450),(30,450),(31,450),(50,450)]:
            with self.subTest(days=age):
                lot.received_on=date(2026,8,1)
                lot.last_stock_date=date(2026,8,1)
                calculated=quote(lot,'dispatch',date(2026,8,1)+timedelta(days=age-1),
                                 100,D('1100'),D('100'))
                self.assertEqual(calculated['charge'], D(1000)*D(rate))
                self.assertEqual(calculated['days'],age)

    def test_tiered_snapshot_survives_price_change_and_partial_exit(self):
        self.tariff.service='tiered'
        for key,value in [('tier_1_10',250),('tier_11_15',300),('tier_16_25',400),
                          ('tier_26_30',450),('tier_31_plus',450)]:
            setattr(self.tariff,key,D(value))
        self.tariff.save()
        lot=receive(self.u,self.intake_data(tariff=self.tariff))
        self.tariff.tier_11_15=D('900')
        self.tariff.save()
        day=date(2026,10,7)
        self.assertEqual(quote(lot,'dispatch',day,100,D('1100'),D('100'))['charge'],D('250000'))
        lot.received_on=date(2026,9,26)
        lot.last_stock_date=date(2026,9,26)
        self.assertEqual(quote(lot,'dispatch',day,100,D('1100'),D('100'))['charge'],D('300000'))

    def test_tiered_form_requires_all_prices_and_no_cross_org_tariff(self):
        from .forms import TariffForm
        d={'camera':self.c1.pk,'name':'Yangi', 'service':'tiered','basis':'net',
           'tier_1_10':'250','tier_11_15':'300','tier_16_25':'400',
           'tier_26_30':'450','tier_31_plus':'450','storage_mode':'prorata'}
        form=TariffForm(self.u,data=d)
        self.assertTrue(form.is_valid(),form.errors)
        self.assertEqual(form.cleaned_data['rate'],D('250'))
        del d['tier_31_plus']
        form=TariffForm(self.u,data=d)
        self.assertFalse(form.is_valid())
        self.assertIn('tier_31_plus',form.errors)
        d['camera']=self.cb.pk
        self.assertFalse(TariffForm(self.u,data=d).is_valid())
    def test_login_throttle(self):
        self.client.logout()
        for i in range(5):self.assertEqual(self.client.post('/admin/login/',{'username':'keeper','password':'incorrect'}).status_code,200)
        self.assertEqual(self.client.post('/admin/login/',{'username':'keeper','password':'incorrect'}).status_code,429)
