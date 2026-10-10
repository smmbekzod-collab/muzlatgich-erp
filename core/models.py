from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction

class Organization(models.Model):
    name = models.CharField('Tashkilot nomi',max_length=160)
    code = models.SlugField('Tashkilot kodi',unique=True)
    camera_limit = models.PositiveIntegerField('Kameralar limiti',default=10,validators=[MinValueValidator(1)])
    is_active = models.BooleanField('Faol',default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        verbose_name = 'Tashkilot'
        verbose_name_plural = 'Tashkilotlar'
    def __str__(self): return self.name
    def clean(self):
        if self.pk and self.cameras.count() > self.camera_limit:
            raise ValidationError({'camera_limit':'Limit mavjud kameralar sonidan kam bo‘la olmaydi. Arxiv kameralar ham hisoblanadi.'})
    def save(self,*args,**kwargs):
        with transaction.atomic():
            if self.pk:
                Organization.objects.select_for_update().get(pk=self.pk)
            self.full_clean()
            return super().save(*args,**kwargs)


class Facility(models.Model):
    """One physical branch / cold-storage warehouse within an organization."""
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name='facilities', verbose_name='Tashkilot')
    code = models.SlugField('Filial kodi', max_length=80)
    name = models.CharField('Filial / ombor nomi', max_length=160)
    region = models.CharField('Viloyat', max_length=120, blank=True)
    district = models.CharField('Tuman / shahar', max_length=120, blank=True)
    address = models.CharField('Manzil', max_length=250, blank=True)
    is_active = models.BooleanField('Faol', default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Filial / ombor'
        verbose_name_plural = 'Filiallar / omborlar'
        ordering = ['organization_id', 'name']
        constraints = [models.UniqueConstraint(fields=['organization', 'code'], name='unique_facility_code_per_org')]

    def __str__(self):
        return f'{self.organization.name} / {self.name}'

    def clean(self):
        if self.pk and Facility.objects.get(pk=self.pk).organization_id != self.organization_id:
            raise ValidationError({'organization': 'Filialni boshqa tashkilotga ko‘chirish mumkin emas.'})

    def save(self, *args, **kwargs):
        with transaction.atomic():
            Organization.objects.select_for_update().get(pk=self.organization_id)
            self.full_clean()
            return super().save(*args, **kwargs)

class Camera(models.Model):
    organization = models.ForeignKey(Organization,on_delete=models.PROTECT,related_name='cameras',verbose_name='Tashkilot')
    facility = models.ForeignKey(Facility, on_delete=models.PROTECT, related_name='cameras', verbose_name='Filial / ombor', null=True, blank=True)
    number = models.PositiveIntegerField('Kamera raqami',validators=[MinValueValidator(1)])
    name = models.CharField('Nomi',max_length=100,blank=True)
    capacity_kg = models.DecimalField('Sig‘imi, kg',max_digits=12,decimal_places=2,null=True,blank=True,validators=[MinValueValidator(0)])
    is_active = models.BooleanField('Faol',default=True)
    class Meta:
        verbose_name = 'Muzlatgich kamerasi'
        verbose_name_plural = 'Muzlatgich kameralari'
        ordering = ['organization_id','facility_id','number']
        constraints = [models.UniqueConstraint(fields=['organization','number'],name='unique_camera_number_per_org')]
    def __str__(self): return f'{self.facility.name if self.facility_id else self.organization.name} / {self.number}-kamera'
    def clean(self):
        if not self.organization_id:return
        if self.facility_id and not Facility.objects.filter(pk=self.facility_id, organization_id=self.organization_id).exists():
            raise ValidationError({'facility':'Filial va kamera bir tashkilotga tegishli bo‘lishi kerak.'})
        if self.pk:
            old = Camera.objects.get(pk=self.pk)
            if old.facility_id != self.facility_id:
                from warehouse.models import Lot
                if Lot.objects.filter(camera_id=self.pk).exists():
                    raise ValidationError({'facility':'Harakatlar tarixi bor kameraning filialini o‘zgartirib bo‘lmaydi.'})
            if old.organization_id != self.organization_id:
                raise ValidationError({'organization':'Kamerani boshqa tashkilotga ko‘chirish mumkin emas.'})
            if not self.is_active:
                from warehouse.models import Lot
                if Lot.objects.filter(camera=self,closed_on__isnull=True).exists():
                    raise ValidationError({'is_active':'Kamerada ochiq yuk bor. Avval chiqarish yoki ko‘chirish kerak.'})
        if not self.pk and Camera.objects.filter(organization_id=self.organization_id).count() >= self.organization.camera_limit:
            raise ValidationError('Tashkilot kamera limitiga yetgan. Avval limitni oshiring.')
    def save(self,*args,**kwargs):
        with transaction.atomic():
            self.organization = Organization.objects.select_for_update().get(pk=self.organization_id)
            if not self.facility_id:
                self.facility, _ = Facility.objects.get_or_create(
                    organization=self.organization, code='main', defaults={'name':'Asosiy ombor'})
            self.full_clean()
            return super().save(*args,**kwargs)

class Membership(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,verbose_name='Foydalanuvchi')
    organization = models.ForeignKey(Organization,on_delete=models.PROTECT,related_name='memberships',verbose_name='Tashkilot')
    role = models.CharField('Lavozim',max_length=20,choices=[('admin','Tashkilot admini'),('keeper','Omborchi'),('accountant','Buxgalter'),('director','Rahbar')],default='admin')
    is_active = models.BooleanField('Ruxsat faol',default=True)
    all_cameras = models.BooleanField('Barcha kameralar (kelgusida qo‘shiladiganlar ham)',default=False)
    all_facilities = models.BooleanField('Barcha filiallar', default=True)
    facilities = models.ManyToManyField(Facility, blank=True, verbose_name='Ruxsat berilgan filiallar')
    cameras = models.ManyToManyField(Camera,blank=True,verbose_name='Ruxsat berilgan kameralar')
    can_receive = models.BooleanField('Yuk qabul qilish',default=False)
    can_dispatch = models.BooleanField('Yuk chiqarish',default=False)
    can_transfer = models.BooleanField('Kameralararo ko‘chirish',default=False)
    can_take_payment = models.BooleanField('To‘lov olish',default=False)
    can_view_finance = models.BooleanField('Moliyaviy hisobotlarni ko‘rish',default=False)
    can_set_tariffs = models.BooleanField('Tarif belgilash',default=False)
    can_dispatch_on_debt = models.BooleanField('Qarzga chiqarish',default=False)
    can_manage_expenses = models.BooleanField('Xarajat kiritish',default=False)
    class Meta:
        verbose_name = 'Administrator ruxsati'
        verbose_name_plural = 'Administratorlar va ruxsatlar'
        constraints = [models.UniqueConstraint(fields=['user','organization'],name='unique_user_org_membership')]
    def __str__(self):return f'{self.user} — {self.organization}'
    def clean(self):
        if self.pk and Membership.objects.get(pk=self.pk).organization_id != self.organization_id:
            raise ValidationError('Ruxsatning tashkilotini almashtirmang. Eski ruxsatni o‘chirib, yangi tashkilot uchun alohida ruxsat yarating.')
        if self.can_dispatch_on_debt and not self.can_dispatch:
            raise ValidationError({'can_dispatch_on_debt':'Avval yuk chiqarish huquqini yoqing.'})
