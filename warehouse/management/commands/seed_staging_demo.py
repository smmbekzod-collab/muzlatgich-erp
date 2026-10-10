"""Deterministic, idempotent staging-only ERP demo seed.

Every record is visibly marked TEST. Never runs in production:
requires explicit flag AND exact isolated Railway staging environment.
Run once from a disposable Railway worker against STAGING Postgres.
"""
import os
import uuid
from datetime import timedelta
from decimal import Decimal as D
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone

from core import access
from core.models import Organization, Facility, Camera, Membership
from core.staff_onboarding import ROLE_RIGHTS, ALL_RIGHTS
from warehouse.models import (
    Customer, Tariff, Lot, Operation, Expense,
    CameraRentalAgreement, CameraRentalInvoice, CameraRentalPayment,
    CameraEnvironmentPolicy, CameraEnvironmentReading, CameraEnvironmentAlert,
)
from warehouse.services import (receive, act, totals, quote, open_camera_rental,
                                issue_camera_rental_invoice, pay_camera_rental_invoice,
                                pending)
from warehouse.monitor_alerts import reconcile_camera

STAGING_ENVIRONMENT_ID = '79dae0a2-be02-4dc2-ac16-3675ffc1aa62'
NAMESPACE = uuid.UUID('e2145c81-457f-46c5-b6a5-679d34e7c927')


def key(label):
    return uuid.uuid5(NAMESPACE, 'MUZLATGICH-ERP-STAGING-DEMO:' + label)


def must_be_staging():
    if (os.environ.get('ALLOW_STAGING_DEMO_SEED')!='1'
        or os.environ.get('RAILWAY_ENVIRONMENT_ID') != STAGING_ENVIRONMENT_ID):
        raise CommandError('Faqat aniq tasdiqlangan Railway STAGING muhitida demo seed mumkin.')
    # SQLite is allowed ONLY inside the Django test runner with explicit test opt-in.
    if connection.vendor != 'postgresql' and not (
        settings.DEBUG and os.environ.get('ALLOW_SEED_SQLITE_TESTS') == '1'):
        raise CommandError('Demo seed faqat PostgreSQL uchun.')


def company(code,name,limit):
    org,created=Organization.objects.get_or_create(
        code=code, defaults={'name':name,'camera_limit':limit})
    if not org.name.startswith('TEST —'):
        raise CommandError('Demo kodini boshqa tashkilot ishlatmoqda. Hech narsa o‘zgartirilmadi.')
    return org


def branch(org,code,name,district):
    f,created=Facility.objects.get_or_create(
        organization=org,code=code,defaults={
            'name':name,'region':'Farg‘ona viloyati',
            'district':district,'address':'TEST — namunaviy manzil, haqiqiy emas'})
    return f


def camera(org,facility,number,capacity,name):
    cam,created=Camera.objects.get_or_create(
        organization=org,facility=facility,number=number,
        defaults={'name':name,'capacity_kg':D(capacity)})
    if cam.organization_id!=org.id or cam.facility_id!=facility.id:
        raise CommandError('Demo kamerasining tashkiloti/filiali mos kelmadi.')
    return cam


def fake_employee(org,role,username,facility=None):
    User=get_user_model()
    user,created=User.objects.get_or_create(
        username=username,defaults={'first_name':'TEST','last_name':role,
            'is_staff':True,'is_active':True})
    if created:
        user.set_unusable_password()
        user.save(update_fields=['password'])
    elif user.is_superuser:
        raise CommandError('Sinov xodimi loginini Super Admin ishlatmoqda.')
    rights={right:right in ROLE_RIGHTS[role] for right in ALL_RIGHTS}
    membership,created=Membership.objects.get_or_create(
        user=user,organization=org,
        defaults={'role':role,'all_cameras':True,'all_facilities':not bool(facility),
                  **rights})
    if created and facility:
        membership.facilities.set([facility])
    return user


def customer(org,name):
    obj,_=Customer.objects.get_or_create(
        organization=org,name=name,
        defaults={'phone':'','note':'TEST ma’lumot, haqiqiy mijoz emas'})
    return obj


def tariff(org,created_by,name):
    defaults={'service':'tiered','basis':'net','rate':D('0'),
        'tier_1_10':D('250'),'tier_11_15':D('300'),
        'tier_16_25':D('400'),'tier_26_30':D('450'),
        'tier_31_plus':D('450'),'storage_mode':'prorata',
        'bill_exit_day':True,'created_by':created_by}
    obj,_=Tariff.objects.get_or_create(organization=org,name=name,defaults=defaults)
    if obj.service!='tiered':
        raise CommandError('Namuna tarif kodi oldindan boshqa turda yaratilgan.')
    return obj


def intake(created_by,label,cam,cust,rate,product,variety,start,boxes,gross,tare):
    idem=key('intake:'+label)
    old=Lot.objects.filter(create_key=idem).first()
    if old:return old
    return receive(created_by,{
        'request_key':idem,'camera':cam,'customer':cust,'tariff':rate,
        'product':product,'variety':variety,'box_type':'TEST yog‘och yashik',
        'date':start,'boxes':boxes,'gross':D(gross),'tare':D(tare),
        'note':'[TEST-SEED] Bu haqiqiy yuk emas.'})


def reading(admin,cam,temp,humid):
    marker=f'[TEST-SEED] kamera {cam.id}'
    old=CameraEnvironmentReading.objects.filter(camera=cam,note=marker).first()
    if not old:
        old=CameraEnvironmentReading.objects.create(
            camera=cam,measured_at=timezone.now()-timedelta(minutes=3),
            temperature=D(temp),humidity=D(humid),note=marker,recorded_by=admin)
    reconcile_camera(cam.id)
    return old


@transaction.atomic
def create_demo():
    root=get_user_model().objects.filter(is_active=True,is_superuser=True).order_by('pk').first()
    if root is None:
        raise CommandError('Avval STAGING Super Admin hisobini yarating.')

    today=timezone.localdate()
    org=company('test-agrostar-holadelnik','TEST — Agro Star Muzlatkich ERP',12)
    other=company('test-izolyatsiya-ombor','TEST — Izolyatsiya Tashkiloti',4)
    f1=branch(org,'test-oltiariq','TEST Oltiariq asosiy ombor','Oltiariq tumani')
    f2=branch(org,'test-quva','TEST Quva filiali','Quva tumani')
    f3=branch(other,'test-begona','TEST Mustaqil filial','Boshqa tuman')
    c1=camera(org,f1,1,'23000','TEST Uzum sovutish')
    c2=camera(org,f1,2,'20000','TEST Meva saqlash')
    c3=camera(org,f2,1,'30000','TEST Oylik ijara')
    c4=camera(org,f2,2,'15000','TEST Bo‘sh kamera')
    c5=camera(other,f3,1,'11000','TEST Boshqa tashkilot kamerasi')

    admin=fake_employee(org,'admin','demo_agro_admin')
    keeper=fake_employee(org,'keeper','demo_agro_omborchi',f1)
    fake_employee(org,'accountant','demo_agro_buxgalter')
    fake_employee(org,'director','demo_agro_rahbar')
    foreign=fake_employee(other,'keeper','demo_begona_omborchi')
    clients=[customer(org,x) for x in (
        'TEST MIJOZ 01 — Uzum',
        'TEST MIJOZ 02 — Olma',
        'TEST MIJOZ 03 — Ijarachi')]
    other_customer=customer(other,'TEST MIJOZ — Begona')
    kg=tariff(org,root,'TEST — bosqichli 1–30 kun')
    kg_other=tariff(other,root,'TEST — boshqa tashkilot tarifi')

    a=intake(root,'uzum250',c1,clients[0],kg,'Uzum','Kishmish',
             today-timedelta(days=3),250,'2750','250')
    b=intake(root,'uzum60',c1,clients[0],kg,'Uzum','Husayni',
             today-timedelta(days=12),60,'720','60')
    c=intake(root,'olma80',c2,clients[1],kg,'Olma','Golden',
             today-timedelta(days=20),80,'920','80')
    d=intake(root,'olma90',c2,clients[1],kg,'Olma','Fuji',
             today-timedelta(days=27),90,'900','90')
    other_lot=intake(root,'other',c5,other_customer,kg_other,'Uzum','TEST',
             today-timedelta(days=5),30,'350','30')

    # Exactly 100 of 250 boxes out, 150 remain, full service charge paid.
    dispatch_key=key('dispatch:uzum250:100')
    if not Operation.objects.filter(request_key=dispatch_key).exists():
        act(root,a.pk,'dispatch',{'request_key':dispatch_key,'date':today,
            'boxes':100,'gross':D('1100'),'tare':D('100'),
            'payment':D('250000'),'payment_method':'cash',
            'note':'[TEST-SEED] 100 yashik chiqim, 150 qoldiq'})

    # The rented camera is independent of lot-based tariffs.
    agreement=CameraRentalAgreement.objects.filter(
        camera=c3,customer=clients[2],start_on=today-timedelta(days=8)).first()
    if agreement is None:
        agreement=open_camera_rental(root,{'camera':c3,'customer':clients[2],
           'start_on':today-timedelta(days=8),'end_on':None,
           'monthly_rate':D('20000000')})
    rent_tariff=Tariff.objects.get(organization=org,service='rental',is_active=True)
    rent_a=intake(root,'rent-a',c3,clients[2],rent_tariff,'Uzum','Toifi',
         today-timedelta(days=6),120,'1320','120')
    rent_b=intake(root,'rent-b',c3,clients[2],rent_tariff,'Anor','TEST',
         today-timedelta(days=4),50,'550','50')
    invoice_key=key('rental-invoice:first')
    invoice=CameraRentalInvoice.objects.filter(request_key=invoice_key).first()
    if not invoice:
        invoice=issue_camera_rental_invoice(root,agreement.pk,invoice_key)
    payment_key=key('rental-payment:five-million')
    if not CameraRentalPayment.objects.filter(request_key=payment_key).exists():
        pay_camera_rental_invoice(root,invoice.pk,payment_key,D('5000000'),'bank',today)
    expense_key=key('electricity-expense')
    Expense.objects.get_or_create(request_key=expense_key,defaults={
        'organization':org,'camera':c1,'date':today,'category':'Elektr energiyasi',
        'description':'[TEST-SEED] Namunaviy elektr energiya xarajati',
        'amount':D('120000'),'created_by':root})

    for cam,limit in ((c1,20),(c2,25),(c3,30),(c4,30),(c5,30)):
        CameraEnvironmentPolicy.objects.get_or_create(
            camera=cam,defaults={
                'min_temperature':D('-1'),'max_temperature':D('2'),
                'min_humidity':D('75'),'max_humidity':D('95'),
                'check_interval_hours':12,'max_storage_days':limit,'updated_by':root})
    # One intentionally above configured threshold; one above age threshold.
    reading(root,c1,'4.5','88')
    reading(root,c2,'1','86')
    reading(root,c3,'0','83')
    reading(root,c5,'1','82')
    reconcile_camera(c4.pk)

    a.refresh_from_db()
    assert a.boxes==150 and a.net==D('1500'), 'Partial dispatch did not leave 150 boxes / 1500 net kg'
    op=Operation.objects.get(request_key=dispatch_key)
    assert op.charge==D('250000'), 'Expected 1000 net kg x 250'
    assert invoice.amount==D('20000000') and invoice.debt==D('15000000'), 'Rental settlement mismatch'
    assert pending(rent_a)==0 and pending(rent_b)==0, 'Rental lots must not charge by kg'
    assert not access.cameras(keeper).filter(pk=c3.pk).exists(), 'Branch scope leaked another facility'
    assert not access.cameras(keeper).filter(pk=c5.pk).exists(), 'Cross-tenant isolation failed'
    assert not access.cameras(foreign).filter(pk=c1.pk).exists(), 'Reverse tenant leakage'
    assert CameraEnvironmentAlert.objects.filter(camera=c1,kind='temp_high',
        resolved_at__isnull=True).exists(), 'Temperature alert missing'
    assert CameraEnvironmentAlert.objects.filter(camera=c2,kind='age',
        resolved_at__isnull=True).exists(), 'Storage age alert missing'
    assert not CameraEnvironmentReading.objects.filter(camera=c4).exists(), 'Empty test camera should remain unmeasured'

    return {
        'organizations':2,'facilities':3,'cameras':5,
        'test_employees':5,'customers':4,'lots':7,'dispatch_boxes':100,
        'boxes_remaining':150,'dispatch_charge':str(op.charge),
        'rental_monthly':str(invoice.amount),'rental_paid':str(invoice.paid),
        'rental_due':str(invoice.debt),
        'main_org_code':org.code,'main_org_id':org.pk,
        'camera_1_id':c1.pk,'rental_camera_id':c3.pk,
        'temperature_alerts':CameraEnvironmentAlert.objects.filter(
            camera__organization=org,resolved_at__isnull=True).count(),
    }


class Command(BaseCommand):
    help='Seed isolated TEST organizations, cameras, clients, shipments, rent, roles and monitoring.'
    def add_arguments(self,parser):
        parser.add_argument('--apply',action='store_true',help='Explicitly permit DB writes.')
    def handle(self,*args,**options):
        must_be_staging()
        if not options['apply']:
            self.stdout.write('STAGING guard OK. No rows written. Run with --apply to create demo.')
            return
        import json
        report=create_demo()
        self.stdout.write('STAGING DEMO COMPLETED '+json.dumps(report,ensure_ascii=False,sort_keys=True))
        self.stdout.write('Test staff passwords are unusable until Super Admin sets them.')
