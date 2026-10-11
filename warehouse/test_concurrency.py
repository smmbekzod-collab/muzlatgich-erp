"""Concurrent warehouse operations against disposable PostgreSQL CI database ONLY.

No Railway credentials or customer data. The seeded data are explicitly TEST.
"""
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection, close_old_connections, connections
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from warehouse.models import Lot, Operation
from warehouse.services import act, totals
from warehouse.management.commands.seed_staging_demo import create_demo, key


@skipUnless(connection.vendor == 'postgresql', 'Real row-locking tests require PostgreSQL')
@override_settings(DEBUG=True)
class PostgreSQLConcurrentOperationsTests(TransactionTestCase):
    databases = {'default'}

    def setUp(self):
        self.root = get_user_model().objects.create_superuser(
            username='ci_concurrency_owner', password='ci-temporary-only-password')
        create_demo()  # Django isolated TEST DB, not a Railway environment.
        self.lot = Lot.objects.get(create_key=key('intake:uzum60'))

    def execute_together(self, kind, data_a, data_b):
        barrier = Barrier(2)
        root_id, lot_id = self.root.pk, self.lot.pk

        def worker(data):
            close_old_connections()
            try:
                user = get_user_model().objects.get(pk=root_id)
                barrier.wait(timeout=20)
                op = act(user, lot_id, kind, data)
                return ('ok', str(op.pk))
            except Exception as exc:
                return ('error', type(exc).__name__, str(exc))
            finally:
                connections['default'].close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            tasks = [pool.submit(worker, data) for data in (data_a, data_b)]
            return [task.result(timeout=30) for task in tasks]

    def test_competing_dispatches_cannot_overdraw_stock(self):
        def request():
            return {
                'request_key':uuid.uuid4(),
                'date':timezone.localdate(),
                'boxes':40,
                'gross':Decimal('480'),
                'tare':Decimal('40'),
                'payment':Decimal('0'),
                'payment_method':'cash',
            }
        results = self.execute_together('dispatch', request(), request())
        self.assertEqual(sum(x[0]=='ok' for x in results),1,results)
        self.assertEqual(sum(x[:2]==('error','ValidationError') for x in results),1,results)
        self.lot.refresh_from_db()
        self.assertEqual((self.lot.boxes,self.lot.net),(20,Decimal('220')))
        self.assertEqual(Operation.objects.filter(lot=self.lot,kind='dispatch').count(),1)
        self.assertEqual(totals(self.lot)['charged'],Decimal('132000'))

    def test_simultaneous_duplicate_requests_charge_and_dispatch_once(self):
        same_key = uuid.uuid4()
        payload = {
            'request_key':same_key,
            'date':timezone.localdate(),
            'boxes':40,
            'gross':Decimal('480'),
            'tare':Decimal('40'),
            'payment':Decimal('132000'),
            'payment_method':'cash',
        }
        results = self.execute_together('dispatch',payload.copy(),payload.copy())
        self.assertEqual(sum(x[0]=='ok' for x in results),2,results)
        self.assertEqual(results[0][1],results[1][1])
        self.assertEqual(Operation.objects.filter(lot=self.lot,kind='dispatch').count(),1)
        self.lot.refresh_from_db()
        self.assertEqual(self.lot.boxes,20)
        self.assertEqual(totals(self.lot)['paid'],Decimal('132000'))
        self.assertEqual(totals(self.lot)['debt'],Decimal('0'))

    def test_two_different_simultaneous_payments_both_recorded(self):
        def request():
            return {'request_key':uuid.uuid4(),
                    'date':timezone.localdate(),
                    'payment':Decimal('1000'),
                    'payment_method':'cash'}
        results=self.execute_together('payment',request(),request())
        self.assertEqual(sum(x[0]=='ok' for x in results),2,results)
        self.assertEqual(Operation.objects.filter(lot=self.lot,kind='payment').count(),2)
        self.assertEqual(totals(self.lot)['paid'],Decimal('2000'))
        self.assertEqual(totals(self.lot)['advance'],Decimal('2000'))
