import uuid
from decimal import Decimal
from django.conf import settings
from django.db import models,transaction
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone
from django.utils import timezone
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
    def current_stay_days(self):
        from django.utils import timezone
        through=self.closed_on or timezone.localdate()
        return max(1,(through-self.received_on).days+1)
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
    @property
    def effective_rate(self):
        if self.lot.service=='tiered':
            age=max(1,self.days)
            field=('tier_1_10' if age<=10 else 'tier_11_15' if age<=15 else
                   'tier_16_25' if age<=25 else 'tier_26_30' if age<=30 else 'tier_31_plus')
            return getattr(self.lot,field)
        return self.lot.rate
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


class CameraEnvironmentPolicy(models.Model):
    """Optional tenant-owned camera limits. No invented defaults for products."""
    camera = models.OneToOneField(
        Camera, on_delete=models.PROTECT, related_name='environment_policy')
    min_temperature = models.DecimalField('Eng past harorat, °C', max_digits=6, decimal_places=2, null=True, blank=True)
    max_temperature = models.DecimalField('Eng yuqori harorat, °C', max_digits=6, decimal_places=2, null=True, blank=True)
    min_humidity = models.DecimalField('Eng past namlik, %', max_digits=5, decimal_places=2, null=True, blank=True)
    max_humidity = models.DecimalField('Eng yuqori namlik, %', max_digits=5, decimal_places=2, null=True, blank=True)
    check_interval_hours = models.PositiveSmallIntegerField('Tekshiruv oralig‘i, soat', default=12)
    max_storage_days = models.PositiveSmallIntegerField(
        'Saqlanish muddatini kuzatish, kun', null=True, blank=True,
        help_text='Ogohlantirish chegarasi. Bu mahsulotning xavfsizligi haqidagi tibbiy yoki laboratoriya xulosasi emas.')
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)

    def clean(self):
        errors = {}
        if self.min_temperature is not None and self.max_temperature is not None and self.min_temperature > self.max_temperature:
            errors['max_temperature'] = 'Yuqori harorat chegarasi pastki chegaradan kichik bo‘la olmaydi.'
        if self.min_humidity is not None and not 0 <= self.min_humidity <= 100:
            errors['min_humidity'] = 'Namlik 0 dan 100 foizgacha bo‘lishi kerak.'
        if self.max_humidity is not None and not 0 <= self.max_humidity <= 100:
            errors['max_humidity'] = 'Namlik 0 dan 100 foizgacha bo‘lishi kerak.'
        if self.min_humidity is not None and self.max_humidity is not None and self.min_humidity > self.max_humidity:
            errors['max_humidity'] = 'Yuqori namlik chegarasi pastki chegaradan kichik bo‘la olmaydi.'
        if not 1 <= self.check_interval_hours <= 168:
            errors['check_interval_hours'] = 'Tekshiruv oralig‘i 1–168 soat bo‘lishi kerak.'
        if self.max_storage_days is not None and not 1 <= self.max_storage_days <= 365:
            errors['max_storage_days'] = 'Nazorat muddati 1–365 kun bo‘lishi kerak.'
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f'{self.camera} / iqlim nazorati'


class CameraEnvironmentReading(models.Model):
    """Immutable manually recorded measurements; IoT is NOT connected."""
    camera = models.ForeignKey(Camera, on_delete=models.PROTECT, related_name='environment_readings')
    measured_at = models.DateTimeField('O‘lchangan vaqt', db_index=True)
    temperature = models.DecimalField('Harorat °C', max_digits=6, decimal_places=2)
    humidity = models.DecimalField('Namlik %', max_digits=5, decimal_places=2)
    note = models.CharField('Izoh', max_length=250, blank=True)
    source = models.CharField('Manba', max_length=12, default='manual', choices=[('manual', 'Qo‘lda'), ('sensor', 'Datchik')])
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-measured_at', '-pk']
        indexes = [models.Index(fields=['camera', '-measured_at'], name='env_camera_time_idx')]
        constraints = [
            models.CheckConstraint(condition=Q(temperature__gte=-80, temperature__lte=80), name='env_temperature_range'),
            models.CheckConstraint(condition=Q(humidity__gte=0, humidity__lte=100), name='env_humidity_range'),
        ]

    def clean(self):
        errors = {}
        if self.temperature is not None and not -80 <= self.temperature <= 80:
            errors['temperature'] = 'Harorat -80 dan +80 °C oralig‘ida bo‘lishi kerak.'
        if self.humidity is not None and not 0 <= self.humidity <= 100:
            errors['humidity'] = 'Namlik 0–100% oralig‘ida bo‘lishi kerak.'
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError('O‘lchov jurnali o‘zgartirilmaydi. Yangi qayd kiriting.')
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.camera} / {self.measured_at:%Y-%m-%d %H:%M}'


class TelegramAlertDestination(models.Model):
    """A chat destination is owned by one organization and managed only by Super Admin."""
    organization=models.OneToOneField(Organization,on_delete=models.PROTECT,related_name='telegram_alerts')
    chat_id=models.CharField('Telegram chat ID',max_length=32)
    enabled=models.BooleanField('Ogohlantirishlarga ruxsat',default=False)
    daily_digest_enabled=models.BooleanField('Ertalabgi kunlik hisobot',default=True)
    updated_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    updated_at=models.DateTimeField(auto_now=True)

    class Meta:
        constraints=[
            models.UniqueConstraint(fields=['chat_id'],condition=Q(enabled=True),
                name='unique_active_telegram_chat')
        ]

    def clean(self):
        if self.enabled and self.chat_id and TelegramAlertDestination.objects.filter(
            chat_id=self.chat_id,enabled=True).exclude(organization_id=self.organization_id).exists():
            raise ValidationError({'chat_id':'Bu Telegram guruhi boshqa faol tashkilotga biriktirilgan.'})
        if self.chat_id and (not self.chat_id.lstrip('-').isdigit() or self.chat_id in ('0','-0')):
            raise ValidationError({'chat_id':'Telegram chat ID raqamlardan iborat bo‘lishi kerak.'})
    def __str__(self):return f'{self.organization} / {self.chat_id}'


class CameraEnvironmentAlert(models.Model):
    """One open incident for each camera/issue; durable Telegram delivery outbox."""
    KINDS=[
        ('temp_low','Past harorat'),('temp_high','Yuqori harorat'),
        ('humidity_low','Past namlik'),('humidity_high','Yuqori namlik'),
        ('stale','O‘lchov eskirgan'),('age','Saqlash nazorat kunidan oshgan'),
    ]
    camera=models.ForeignKey(Camera,on_delete=models.PROTECT,related_name='environment_alerts')
    kind=models.CharField('Hodisa',choices=KINDS,max_length=20)
    description=models.CharField('Sabab',max_length=300)
    opened_at=models.DateTimeField('Boshlandi',default=timezone.now)
    resolved_at=models.DateTimeField('Bartaraf etildi',null=True,blank=True)
    delivery_status=models.CharField('Telegram holati',max_length=15,default='disabled',
        choices=[('disabled','Ulanmagan'),('pending','Navbatda'),('sending','Yuborilmoqda'),('sent','Yuborilgan'),('failed','Xatolik')])
    attempts=models.PositiveSmallIntegerField(default=0)
    next_attempt_at=models.DateTimeField(null=True,blank=True)
    claimed_at=models.DateTimeField(null=True,blank=True)
    sent_at=models.DateTimeField(null=True,blank=True)
    last_error=models.CharField(max_length=120,blank=True)
    class Meta:
        ordering=['-opened_at','-pk']
        constraints=[models.UniqueConstraint(fields=['camera','kind'],condition=Q(resolved_at__isnull=True),
                    name='unique_open_environment_alert')]
        indexes=[models.Index(fields=['delivery_status','next_attempt_at'],name='env_alert_delivery_idx')]
    def __str__(self):return f'{self.camera} · {self.get_kind_display()}'


class DailyTelegramDigest(models.Model):
    """One morning digest per organization and local date; retryable delivery audit."""
    organization=models.ForeignKey(Organization,on_delete=models.PROTECT,related_name='daily_telegram_digests')
    report_date=models.DateField('Hisobot sanasi')
    message=models.TextField('Tashkilotning kunlik hisoboti')
    delivery_status=models.CharField(max_length=12,default='pending',choices=[
        ('pending','Navbatda'),('sending','Yuborilmoqda'),
        ('sent','Yuborilgan'),('failed','Xatolik'),('disabled','To‘xtatilgan')])
    chat_id=models.CharField('Oxirgi yo‘naltirilgan chat',max_length=32,blank=True)
    attempts=models.PositiveSmallIntegerField(default=0)
    next_attempt_at=models.DateTimeField(null=True,blank=True)
    claimed_at=models.DateTimeField(null=True,blank=True)
    sent_at=models.DateTimeField(null=True,blank=True)
    last_error=models.CharField(max_length=120,blank=True)
    created_at=models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering=['-report_date','-pk']
        constraints=[models.UniqueConstraint(fields=['organization','report_date'],name='unique_daily_digest_per_org')]
        indexes=[models.Index(fields=['delivery_status','next_attempt_at'],name='daily_digest_queue_idx')]

    def __str__(self):
        return f'{self.organization} · {self.report_date}'
