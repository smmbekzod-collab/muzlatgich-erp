"""Real PostgreSQL multi-connection races; never write to a live business database.

SQLite CI skips these tests. The staging test runner creates its own throwaway
PostgreSQL database, isolated from staging business rows.
"""
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal as D
from threading import Barrier
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection, connections
from django.test import TransactionTestCase
from django.utils import timezone
from core.models import Organization, Camera
from warehouse.models import Customer, Tariff, Lot, Operation
from warehouse.services import receive, act, totals

POSTGRES = connection.vendor == "postgresql"


@skipUnless(POSTGRES, "Real PostgreSQL SELECT FOR UPDATE required.")
class PostgreSQLConcurrencyTests(TransactionTestCase):
    reset_sequences = False

    def setUp(self):
        self.root = get_user_model().objects.create_superuser(
            username='concurrency_test_admin',password='TEST_ONLY_UseNoOutside!321')
        self.org=Organization.objects.create(name='TEST concurrency isolated DB',code='concurrency-test')
        self.cam=Camera.objects.create(organization=self.org,number=1,capacity_kg=D('10000'))
        self.customer=Customer.objects.create(organization=self.org,name='Concurrency Test Customer')
        self.tariff=Tariff.objects.create(
            organization=self.org,name='Test tier',service='tiered',
            basis='net',rate=D('0'),storage_mode='prorata',bill_exit_day=True,
            tier_1_10=D('250'),tier_11_15=D('300'),tier_16_25=D('400'),
            tier_26_30=D('450'),tier_31_plus=D('450'),created_by=self.root)
        self.today=timezone.localdate()
        self.lot=receive(self.root,self.intake(uuid.uuid4()))

    def intake(self,key):
        return {'request_key':key,'camera':self.cam,'customer':self.customer,
                'tariff':self.tariff,'product':'TEST uzum','variety':'TEST',
                'box_type':'yashik','date':self.today,'boxes':10,
                'gross':D('110'),'tare':D('10'),'note':'CONCURRENCY TEST'}

    def race(self,items,fn):
        gate=Barrier(len(items))
        def worker(item):
            connections.close_all()  # dedicated connection per thread
            try:
                gate.wait(timeout=20)
                return fn(item)
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=len(items)) as pool:
            futures=[pool.submit(worker,item) for item in items]
            return [f.result(timeout=40) for f in futures]

    def test_two_distinct_dispatches_cannot_remove_same_stock_twice(self):
        requests=[uuid.uuid4(),uuid.uuid4()]
        def dispatch(key):
            try:
                op=act(self.root,self.lot.pk,'dispatch',{
                    'request_key':key,'date':self.today,
                    'boxes':6,'gross':D('66'),'tare':D('6'),
                    'payment':D('0'),'payment_method':'cash',
                    'note':'STAGING race test'})
                return ('ok',op.pk)
            except ValidationError:
                return ('rejected',None)
        outcomes=self.race(requests,dispatch)
        self.assertEqual(sorted(x[0] for x in outcomes),['ok','rejected'])
        self.lot.refresh_from_db()
        self.assertEqual(self.lot.boxes,4)
        self.assertEqual(self.lot.gross,D('44'))
        self.assertEqual(self.lot.tare,D('4'))
        self.assertEqual(self.lot.net,D('40'))
        self.assertEqual(self.lot.operations.filter(kind='dispatch').count(),1)

    def test_twelve_simultaneous_dispatches_are_serialized_correctly(self):
        """Twelve employees attempt to dispatch from a ten-box lot."""
        keys=[uuid.uuid4() for _ in range(12)]
        def dispatch(key):
            try:
                op=act(self.root,self.lot.pk,'dispatch',{
                    'request_key':key,'date':self.today,
                    'boxes':1,'gross':D('11'),'tare':D('1'),
                    'payment':D('2500'),'payment_method':'cash',
                    'note':'12-user stress'})
                return ('ok',op.pk)
            except ValidationError:
                return ('rejected',None)
        outcomes=self.race(keys,dispatch)
        self.assertEqual(sum(x[0]=='ok' for x in outcomes),10)
        self.assertEqual(sum(x[0]=='rejected' for x in outcomes),2)
        self.lot.refresh_from_db()
        self.assertEqual((self.lot.boxes,self.lot.net),(0,D('0')))
        self.assertIsNotNone(self.lot.closed_on)
        self.assertEqual(self.lot.operations.filter(kind='dispatch').count(),10)
        summary=totals(self.lot)
        self.assertEqual(summary['charged'],D('25000'))
        self.assertEqual(summary['paid'],D('25000'))
        self.assertEqual(summary['debt'],0)

    def test_eight_parallel_distinct_payments_are_all_counted(self):
        keys=[uuid.uuid4() for _ in range(8)]
        def pay(key):
            op=act(self.root,self.lot.pk,'payment',{
                'request_key':key,'date':self.today,'payment':D('100'),
                'payment_method':'bank','note':'parallel independent payments'})
            return op.pk
        results=self.race(keys,pay)
        self.assertEqual(len(set(results)),8)
        self.assertEqual(self.lot.operations.filter(kind='payment').count(),8)
        self.assertEqual(totals(self.lot)['paid'],D('800'))

    def test_duplicate_payment_key_only_records_one_payment(self):
        key=uuid.uuid4()
        def pay(_):
            op=act(self.root,self.lot.pk,'payment',{
                'request_key':key,'date':self.today,'payment':D('1000'),
                'payment_method':'cash','note':'one payment two clicks'})
            return op.pk
        results=self.race([0,1],pay)
        self.assertEqual(results[0],results[1])
        self.assertEqual(self.lot.operations.filter(kind='payment').count(),1)
        self.assertEqual(totals(self.lot)['paid'],D('1000'))

    def test_duplicate_receipt_key_creates_single_lot(self):
        key=uuid.uuid4()
        def receipt(_):
            obj=receive(self.root,self.intake(key))
            return obj.pk
        results=self.race([0,1],receipt)
        self.assertEqual(results[0],results[1])
        self.assertEqual(Lot.objects.filter(create_key=key).count(),1)
        self.assertEqual(Operation.objects.filter(lot_id=results[0],kind='receive').count(),1)
        self.assertEqual(Lot.objects.filter(camera=self.cam,closed_on__isnull=True).count(),2)
