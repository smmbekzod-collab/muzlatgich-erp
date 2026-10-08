import uuid
from decimal import Decimal
from django.conf import settings
from django.db import models
from core.models import Organization,Camera

class Customer(models.Model):
    organization=models.ForeignKey(Organization,on_delete=models.PROTECT)
    name=models.CharField(max_length=150)
    phone=models.CharField(max_length=40,blank=True)
    note=models.CharField(max_length=300,blank=True)
    def __str__(self):return self.name

class Tariff(models.Model):
    organization=models.ForeignKey(Organization,on_delete=models.PROTECT)
    name=models.CharField(max_length=120)
    service=models.CharField(max_length=10,choices=[('cooling','Sovutish'),('storage','Saqlama')])
    basis=models.CharField(max_length=10,choices=[('net','Sof kg'),('gross','Brutto kg')],default='net')
    rate=models.DecimalField(max_digits=16,decimal_places=2)
    storage_mode=models.CharField(max_length=10,choices=[('prorata','Kuniga ulush'),('full','Boshlangan oy to‘liq')],default='prorata')
    bill_exit_day=models.BooleanField(default=False)
    is_active=models.BooleanField(default=True)
    created_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    created_at=models.DateTimeField(auto_now_add=True)
    def __str__(self):return f'{self.name} — {self.rate:,.0f} so‘m'

class Lot(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    create_key=models.UUIDField(unique=True)
    organization=models.ForeignKey(Organization,on_delete=models.PROTECT)
    camera=models.ForeignKey(Camera,on_delete=models.PROTECT)
    customer=models.ForeignKey(Customer,on_delete=models.PROTECT)
    product=models.CharField(max_length=100)
    variety=models.CharField(max_length=100,blank=True)
    box_type=models.CharField(max_length=80)
    received_on=models.DateField()
    last_stock_date=models.DateField()
    initial_boxes=models.PositiveIntegerField()
    initial_gross=models.DecimalField(max_digits=14,decimal_places=3)
    initial_tare=models.DecimalField(max_digits=14,decimal_places=3)
    boxes=models.PositiveIntegerField()
    gross=models.DecimalField(max_digits=14,decimal_places=3)
    tare=models.DecimalField(max_digits=14,decimal_places=3)
    tariff_name=models.CharField(max_length=120)
    service=models.CharField(max_length=10)
    basis=models.CharField(max_length=10)
    rate=models.DecimalField(max_digits=16,decimal_places=2)
    storage_mode=models.CharField(max_length=10)
    bill_exit_day=models.BooleanField(default=False)
    storage_billed=models.DecimalField(max_digits=16,decimal_places=2,default=0)
    closed_on=models.DateField(null=True,blank=True)
    note=models.TextField(blank=True)
    created_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    created_at=models.DateTimeField(auto_now_add=True)
    @property
    def net(self):return self.gross-self.tare
    @property
    def short_id(self):return str(self.id)[:8].upper()
    def __str__(self):return f'{self.short_id} · {self.product}'

class Operation(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    request_key=models.UUIDField(unique=True)
    lot=models.ForeignKey(Lot,on_delete=models.PROTECT,related_name='operations')
    camera=models.ForeignKey(Camera,on_delete=models.PROTECT,related_name='+')
    target_camera=models.ForeignKey(Camera,on_delete=models.PROTECT,null=True,blank=True,related_name='+')
    kind=models.CharField(max_length=12,choices=[('receive','Kirim'),('dispatch','Chiqim'),('loss','Yo‘qotish'),('transfer','Ko‘chirish'),('payment','To‘lov'),('storage_bill','Saqlama hisobi'),('reversal','Bekor qilish')])
    reversal_of=models.OneToOneField('self',on_delete=models.PROTECT,null=True,blank=True,related_name='reversed_by')
    date=models.DateField()
    boxes=models.PositiveIntegerField(default=0)
    gross=models.DecimalField(max_digits=14,decimal_places=3,default=0)
    tare=models.DecimalField(max_digits=14,decimal_places=3,default=0)
    days=models.PositiveIntegerField(default=0)
    charge=models.DecimalField(max_digits=16,decimal_places=2,default=0)
    payment=models.DecimalField(max_digits=16,decimal_places=2,default=0)
    payment_method=models.CharField(max_length=12,blank=True)
    boxes_after=models.PositiveIntegerField(default=0)
    gross_after=models.DecimalField(max_digits=14,decimal_places=3,default=0)
    tare_after=models.DecimalField(max_digits=14,decimal_places=3,default=0)
    note=models.TextField(blank=True)
    created_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    created_at=models.DateTimeField(auto_now_add=True)
    @property
    def net(self):return self.gross-self.tare
    @property
    def short_id(self):return str(self.id)[:8].upper()
    class Meta:ordering=['-created_at']

class Expense(models.Model):
    request_key=models.UUIDField(unique=True)
    organization=models.ForeignKey(Organization,on_delete=models.PROTECT)
    camera=models.ForeignKey(Camera,on_delete=models.PROTECT)
    date=models.DateField()
    category=models.CharField(max_length=50)
    description=models.CharField(max_length=300)
    amount=models.DecimalField(max_digits=16,decimal_places=2)
    created_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    created_at=models.DateTimeField(auto_now_add=True)

class LoginThrottle(models.Model):
    key=models.CharField(max_length=64,primary_key=True)
    attempts=models.PositiveIntegerField(default=0)
    since=models.DateTimeField()
