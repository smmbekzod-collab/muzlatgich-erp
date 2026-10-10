import uuid
import django.db.models.deletion
from django.db import migrations,models
from django.conf import settings
from django.db.models import Q
class Migration(migrations.Migration):
    dependencies=[('warehouse','0003_tiered_storage_tariffs'),migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations=[
       migrations.AlterField(model_name='tariff',name='service',field=models.CharField(max_length=10,choices=[
          ('cooling','Sovutish (eski tarif)'),('storage','Saqlama (eski tarif)'),
          ('tiered','Muddatga ko‘ra, so‘m/kg'),('rental','Kamera ijarasi (yuk uchun 0 so‘m)')])),
       migrations.CreateModel(name='CameraRentalAgreement',fields=[
          ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),
          ('start_on',models.DateField(verbose_name='Ijara boshlanish sanasi')),
          ('end_on',models.DateField(blank=True,null=True,verbose_name='Ijara tugash sanasi')),
          ('monthly_rate',models.DecimalField(max_digits=16,decimal_places=2,verbose_name='Oylik ijara, so‘m')),
          ('created_at',models.DateTimeField(auto_now_add=True)),
          ('camera',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name='rental_agreements',to='core.camera')),
          ('customer',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name='rental_agreements',to='warehouse.customer')),
          ('created_by',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,to=settings.AUTH_USER_MODEL)),
       ],options={'ordering':['-start_on','-id']}),
       migrations.AddConstraint(model_name='camerarentalagreement',constraint=models.CheckConstraint(condition=Q(monthly_rate__gt=0),name='rental_positive_rate')),
       migrations.CreateModel(name='CameraRentalRateChange',fields=[
          ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),
          ('effective_from',models.DateField(verbose_name='Qaysi oydan')),
          ('monthly_rate',models.DecimalField(max_digits=16,decimal_places=2,verbose_name='Yangi oylik ijara, so‘m')),
          ('created_at',models.DateTimeField(auto_now_add=True)),
          ('agreement',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name='rate_changes',to='warehouse.camerarentalagreement')),
          ('created_by',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,to=settings.AUTH_USER_MODEL)),
       ]),
       migrations.AddConstraint(model_name='camerarentalratechange',constraint=models.UniqueConstraint(fields=['agreement','effective_from'],name='unique_rental_change_date')),
       migrations.AddConstraint(model_name='camerarentalratechange',constraint=models.CheckConstraint(condition=Q(monthly_rate__gt=0),name='rental_change_gt_zero')),
       migrations.CreateModel(name='CameraRentalInvoice',fields=[
          ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),
          ('period_start',models.DateField(verbose_name='Davr boshi')),
          ('period_end',models.DateField(verbose_name='Davr oxiri')),
          ('amount',models.DecimalField(max_digits=16,decimal_places=2,verbose_name='Hisob, so‘m')),
          ('request_key',models.UUIDField(default=uuid.uuid4,unique=True)),
          ('created_at',models.DateTimeField(auto_now_add=True)),
          ('agreement',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name='invoices',to='warehouse.camerarentalagreement')),
          ('created_by',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,to=settings.AUTH_USER_MODEL)),
       ],options={'ordering':['-period_start']}),
       migrations.AddConstraint(model_name='camerarentalinvoice',constraint=models.UniqueConstraint(fields=['agreement','period_start'],name='unique_camera_invoice_period')),
       migrations.CreateModel(name='CameraRentalPayment',fields=[
          ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),
          ('request_key',models.UUIDField(default=uuid.uuid4,unique=True)),
          ('amount',models.DecimalField(max_digits=16,decimal_places=2,verbose_name='To‘lov, so‘m')),
          ('method',models.CharField(choices=[('cash','Naqd'),('bank','O‘tkazma'),('card','Karta')],max_length=12,verbose_name='To‘lov turi')),
          ('date',models.DateField(verbose_name='Sana')),
          ('created_at',models.DateTimeField(auto_now_add=True)),
          ('invoice',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name='payments',to='warehouse.camerarentalinvoice')),
          ('created_by',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,to=settings.AUTH_USER_MODEL)),
       ],options={'ordering':['-created_at']}),
       migrations.AddConstraint(model_name='camerarentalpayment',constraint=models.CheckConstraint(condition=Q(amount__gt=0),name='rental_payment_gt_zero')),
       migrations.AddField(model_name='lot',name='rental_agreement',field=models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.PROTECT,related_name='lots',to='warehouse.camerarentalagreement')),
    ]
