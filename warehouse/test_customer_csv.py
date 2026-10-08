from django.test import TestCase
from django.contrib.auth import get_user_model
from core.models import Organization, Camera, Membership
from warehouse.models import Customer, Lot, Operation
from django.utils import timezone
import uuid
from decimal import Decimal as D

class CustomerCsvTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user('reporter',password='test-Password-123')
        self.org=Organization.objects.create(name='Demo',code='demo',camera_limit=2)
        self.cam=Camera.objects.create(organization=self.org,number=1)
        Membership.objects.create(user=self.user,organization=self.org,all_cameras=True,can_view_finance=True)
        self.customer=Customer.objects.create(organization=self.org,name='=HARMLESS',phone='123')
        self.lot=Lot.objects.create(organization=self.org,camera=self.cam,customer=self.customer,create_key=uuid.uuid4(),product='Uzum',variety='Kishmish',box_type='Quti',received_on=timezone.localdate(),last_stock_date=timezone.localdate(),initial_boxes=10,initial_gross=D('100'),initial_tare=D('10'),boxes=10,gross=D('100'),tare=D('10'),tariff_name='Tarif',service='cooling',basis='net',rate=10,storage_mode='prorata',created_by=self.user)
        Operation.objects.create(lot=self.lot,camera=self.cam,request_key=uuid.uuid4(),kind='receive',date=timezone.localdate(),boxes=10,gross=D('100'),tare=D('10'),boxes_after=10,gross_after=D('100'),tare_after=D('10'),created_by=self.user)
    def test_export_and_formula_escaping(self):
        self.client.force_login(self.user)
        result=self.client.get('/app/report/customers.csv')
        self.assertEqual(result.status_code,200)
        self.assertIn('Kishmish',result.content.decode('utf-8-sig'))
        self.assertIn("'=HARMLESS",result.content.decode('utf-8-sig'))
    def test_no_permission(self):
        Membership.objects.filter(user=self.user).update(can_view_finance=False)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get('/app/report/customers.csv').status_code,403)
