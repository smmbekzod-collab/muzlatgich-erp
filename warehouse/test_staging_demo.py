"""Tests for the locked-to-staging demo seed. No network or real Telegram calls."""
from io import StringIO
from unittest.mock import patch
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase,override_settings
from django.contrib.auth import get_user_model
from core.models import Camera,Facility,Membership,Organization
from warehouse.models import (
    Customer,Lot,Operation,CameraRentalInvoice,CameraRentalPayment,
    CameraEnvironmentAlert,CameraEnvironmentReading,Expense
)
from warehouse.services import totals
from decimal import Decimal as D

STAGE_ENV={'ALLOW_STAGING_DEMO_SEED':'1',
           'RAILWAY_ENVIRONMENT_ID':'79dae0a2-be02-4dc2-ac16-3675ffc1aa62',
           'ALLOW_SEED_SQLITE_TESTS':'1'}

@override_settings(DEBUG=True,
    STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},
              'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class DemoSeedTests(TestCase):
    def setUp(self):
        self.owner=get_user_model().objects.create_superuser(
            'test_demo_superuser',password='SuperStrongForTesting!99')

    def test_requires_explicit_staging_environment(self):
        with patch.dict('os.environ',{},clear=True):
            with self.assertRaises(CommandError):
                call_command('seed_staging_demo','--apply',verbosity=0)
        self.assertEqual(Organization.objects.count(),0)

    @patch.dict('os.environ',STAGE_ENV)
    def test_default_dry_run_writes_nothing(self):
        out=StringIO()
        call_command('seed_staging_demo',stdout=out,verbosity=0)
        self.assertIn('No rows written',out.getvalue())
        self.assertEqual(Organization.objects.count(),0)

    @patch.dict('os.environ',STAGE_ENV)
    def test_seed_full_demo_idempotent_and_scoped(self):
        out=StringIO()
        call_command('seed_staging_demo','--apply',stdout=out,verbosity=0)
        self.assertIn('STAGING DEMO COMPLETED',out.getvalue())
        self.assertEqual(Organization.objects.count(),2)
        self.assertEqual(Facility.objects.count(),3)
        self.assertEqual(Camera.objects.count(),5)
        self.assertEqual(Customer.objects.count(),4)
        self.assertEqual(Lot.objects.count(),7)
        self.assertEqual(CameraEnvironmentReading.objects.count(),4)
        self.assertEqual(CameraRentalInvoice.objects.count(),1)
        self.assertEqual(CameraRentalPayment.objects.count(),1)
        self.assertEqual(Expense.objects.count(),1)
        for username in ['demo_agro_admin','demo_agro_omborchi','demo_agro_buxgalter','demo_agro_rahbar','demo_begona_omborchi']:
            user=get_user_model().objects.get(username=username)
            self.assertFalse(user.has_usable_password())
            self.assertFalse(user.is_superuser)
            self.assertEqual(Membership.objects.filter(user=user).count(),1)
        lot=Lot.objects.get(note__contains='Bu haqiqiy yuk emas',initial_boxes=250)
        self.assertEqual(lot.boxes,150)
        self.assertEqual(lot.net,D('1500'))
        self.assertEqual(totals(lot)['charged'],D('250000'))
        self.assertEqual(totals(lot)['paid'],D('250000'))
        invoice=CameraRentalInvoice.objects.get()
        self.assertEqual(invoice.amount,D('20000000'))
        self.assertEqual(invoice.debt,D('15000000'))
        self.assertTrue(CameraEnvironmentAlert.objects.filter(kind='temp_high',resolved_at__isnull=True).exists())
        self.assertTrue(CameraEnvironmentAlert.objects.filter(kind='age',resolved_at__isnull=True).exists())
        self.client.force_login(self.owner)
        for path in ['/app/','/app/platform/','/app/report/','/app/monitor/','/app/monitor/director/','/app/rentals/','/app/platform/staff/']:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code,200)
        counts=(Organization.objects.count(),Camera.objects.count(),
            Lot.objects.count(),Operation.objects.count(),
            CameraEnvironmentReading.objects.count(),
            CameraEnvironmentAlert.objects.count())
        call_command('seed_staging_demo','--apply',stdout=StringIO(),verbosity=0)
        new_counts=(Organization.objects.count(),Camera.objects.count(),
            Lot.objects.count(),Operation.objects.count(),
            CameraEnvironmentReading.objects.count(),
            CameraEnvironmentAlert.objects.count())
        self.assertEqual(counts,new_counts)
