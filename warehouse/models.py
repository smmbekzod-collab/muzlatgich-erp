import uuid
from decimal import Decimal
from django.conf import settings
from django.db import models,transaction
from django.core.exceptions import ValidationError
from django.db.models import Q
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
    service=models.CharField(max_length=10,choices=[('cooling','Sovutish (eski tarif)'),('storage','Saqlama (eski tarif)'),('tiered','Muddatga ko‘ra, so‘m/kg'),('rental','Kamera ijarasi (yuk uchun 0 so‘m)')])
    tier_1_10=models.DecimalField('1–10 kun, so‘m/kg',max_digits=16,decimal_places=2,null=True,blank=True)
    tier_11_15=models.DecimalField('11–15 kun, so‘m/kg',max_digits=16,decimal_places=2,null=True,blank=True)
    tier_16_25=models.DecimalField('16–25 kun, so‘m/kg',max_digits=16,decimal_places=2,null=True,blank=True)
    tier_26_30=models.DecimalField('26–30 kun, so‘m/kg',max_digits=16,decimal_places=2,null=True,blank=True)
    tier_31_plus=models.DecimalField('31+ kun, so‘m/kg',max_digits=16,decimal_places=2,null=True,blank=True)

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
    rental_agreement=models.ForeignKey('CameraRentalAgreement',on_delete=models.PROTECT,null=True,blank=True,related_name='lots')
    tier_1_10=models.DecimalField('1–10 kun, so‘m/kg',max_digits=16,decimal_places=2,null=True,blank=True)
    tier_11_15=models.DecimalField('11–15 kun, so‘m/kg',max_digits=16,decimal_places=2,null=True,blank=True)
    tier_16_25=models.DecimalField('16–25 kun, so‘m/kg',max_digits=16,decimal_places=2,null=True,blank=True)
    tier_26_30=models.DecimalField('26–30 kun, so‘m/kg',max_digits=16,decimal_places=2,null=True,blank=True)
    tier_31_plus=models.DecimalField('31+ kun, so‘m/kg',max_digits=16,decimal_places=2,null=True,blank=True)

    closed_on=models.DateField(null=True,blank=True)
    note=models.TextField(blank=True)
    created_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    created_at=models.DateTimeField(auto_now_add=True)
    @property
    def net(self):return self.gross-self.tare
    @property
    def short_id(self):return str(self.id)[:8].upper()
    @property
    def rate_description(self):
        if self.service=='rental':
            return 'Kamera ijara sharti bo‘yicha, partiya uchun 0 so‘m'
        if self.service=='tiered':
            return ' | '.join([f'{period}: {getattr(self,field):,.0f} so‘m/kg'
              for period,field in [('1–10','tier_1_10'),('11–15','tier_11_15'),
                     ('16–25','tier_16_25'),('26–30','tier_26_30'),('31+','tier_31_plus')]
              if getattr(self,field) is not None])
        return f'{self.rate:,.0f} so‘m/' + ('kg/kun' if self.service=='cooling' else 'oy')
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

class CameraRentalAgreement(models.Model):
    """Fixed price per camera, independent of the number of stored lots."""
    camera=models.ForeignKey(Camera,on_delete=models.PROTECT,related_name='rental_agreements')
    customer=models.ForeignKey(Customer,on_delete=models.PROTECT,related_name='rental_agreements')
    start_on=models.DateField('Ijara boshlanish sanasi')
    end_on=models.DateField('Ijara tugash sanasi',null=True,blank=True)
    monthly_rate=models.DecimalField('Oylik ijara, so‘m',max_digits=16,decimal_places=2)
    created_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering=['-start_on','-id']
        constraints=[models.CheckConstraint(condition=Q(monthly_rate__gt=0),name='rental_positive_rate')]
    def clean(self):
        if self.camera_id and self.customer_id and self.camera.organization_id!=self.customer.organization_id:
            raise ValidationError({'customer':'Mijoz va kamera bir tashkilotga tegishli bo‘lishi kerak.'})
        if self.end_on and self.start_on and self.end_on<self.start_on:
            raise ValidationError({'end_on':'Tugash sanasi boshlanishidan oldin.'})
        if self.camera_id and self.start_on:
            qs=CameraRentalAgreement.objects.filter(camera_id=self.camera_id)
            if self.pk:qs=qs.exclude(pk=self.pk)
            if self.end_on:qs=qs.filter(start_on__lte=self.end_on)
            if qs.filter(Q(end_on__isnull=True)|Q(end_on__gte=self.start_on)).exists():
                raise ValidationError('Kamera bu davrda boshqa ijara shartiga biriktirilgan.')
    def save(self,*args,**kwargs):
        with transaction.atomic():
            Camera.objects.select_for_update().get(pk=self.camera_id)
            if self.pk:
                previous=CameraRentalAgreement.objects.get(pk=self.pk)
                if (previous.camera_id!=self.camera_id or previous.customer_id!=self.customer_id
                        or previous.start_on!=self.start_on or previous.monthly_rate!=self.monthly_rate):
                    raise ValidationError('Boshlang‘ich ijara narxini orqaga o‘zgartirib bo‘lmaydi. Yangi narx keyingi oydan belgilanadi.')
            self.full_clean()
            return super().save(*args,**kwargs)
    def rate_on(self,start):
        update=self.rate_changes.filter(effective_from__lte=start).order_by('-effective_from').first()
        return update.monthly_rate if update else self.monthly_rate
    def __str__(self):return f'{self.camera} · {self.customer}'

class CameraRentalRateChange(models.Model):
    agreement=models.ForeignKey(CameraRentalAgreement,on_delete=models.PROTECT,related_name='rate_changes')
    effective_from=models.DateField('Qaysi oydan')
    monthly_rate=models.DecimalField('Yangi oylik ijara, so‘m',max_digits=16,decimal_places=2)
    created_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['agreement','effective_from'],name='unique_rental_change_date'),
                     models.CheckConstraint(condition=Q(monthly_rate__gt=0),name='rental_change_gt_zero')]

class CameraRentalInvoice(models.Model):
    agreement=models.ForeignKey(CameraRentalAgreement,on_delete=models.PROTECT,related_name='invoices')
    period_start=models.DateField('Davr boshi')
    period_end=models.DateField('Davr oxiri')
    amount=models.DecimalField('Hisob, so‘m',max_digits=16,decimal_places=2)
    request_key=models.UUIDField(unique=True,default=uuid.uuid4)
    created_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering=['-period_start']
        constraints=[models.UniqueConstraint(fields=['agreement','period_start'],name='unique_camera_invoice_period')]
    @property
    def paid(self):
        from django.db.models import Sum
        return self.payments.aggregate(s=Sum('amount'))['s'] or Decimal('0')
    @property
    def debt(self):return max(Decimal('0'),self.amount-self.paid)

class CameraRentalPayment(models.Model):
    invoice=models.ForeignKey(CameraRentalInvoice,on_delete=models.PROTECT,related_name='payments')
    request_key=models.UUIDField(unique=True,default=uuid.uuid4)
    amount=models.DecimalField('To‘lov, so‘m',max_digits=16,decimal_places=2)
    method=models.CharField('To‘lov turi',max_length=12,choices=[('cash','Naqd'),('bank','O‘tkazma'),('card','Karta')])
    date=models.DateField('Sana')
    created_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering=['-created_at']
        constraints=[models.CheckConstraint(condition=Q(amount__gt=0),name='rental_payment_gt_zero')]
