import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.db.models import Q

class Migration(migrations.Migration):
    dependencies = [
        ('core', '0004_membership_can_monitor_environment'),
        ('warehouse', '0004_camera_rentals'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(name='CameraEnvironmentPolicy',fields=[
            ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),
            ('min_temperature',models.DecimalField(blank=True,decimal_places=2,max_digits=6,null=True,verbose_name='Eng past harorat, °C')),
            ('max_temperature',models.DecimalField(blank=True,decimal_places=2,max_digits=6,null=True,verbose_name='Eng yuqori harorat, °C')),
            ('min_humidity',models.DecimalField(blank=True,decimal_places=2,max_digits=5,null=True,verbose_name='Eng past namlik, %')),
            ('max_humidity',models.DecimalField(blank=True,decimal_places=2,max_digits=5,null=True,verbose_name='Eng yuqori namlik, %')),
            ('check_interval_hours',models.PositiveSmallIntegerField(default=12,verbose_name='Tekshiruv oralig‘i, soat')),
            ('max_storage_days',models.PositiveSmallIntegerField(blank=True,help_text='Ogohlantirish chegarasi. Bu mahsulotning xavfsizligi haqidagi tibbiy yoki laboratoriya xulosasi emas.',null=True,verbose_name='Saqlanish muddatini kuzatish, kun')),
            ('updated_at',models.DateTimeField(auto_now=True)),
            ('camera',models.OneToOneField(on_delete=django.db.models.deletion.PROTECT,related_name='environment_policy',to='core.camera')),
            ('updated_by',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,to=settings.AUTH_USER_MODEL)),
        ]),
        migrations.CreateModel(name='CameraEnvironmentReading',fields=[
            ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),
            ('measured_at',models.DateTimeField(db_index=True,verbose_name='O‘lchangan vaqt')),
            ('temperature',models.DecimalField(decimal_places=2,max_digits=6,verbose_name='Harorat °C')),
            ('humidity',models.DecimalField(decimal_places=2,max_digits=5,verbose_name='Namlik %')),
            ('note',models.CharField(blank=True,max_length=250,verbose_name='Izoh')),
            ('source',models.CharField(choices=[('manual','Qo‘lda'),('sensor','Datchik')],default='manual',max_length=12,verbose_name='Manba')),
            ('created_at',models.DateTimeField(auto_now_add=True)),
            ('camera',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name='environment_readings',to='core.camera')),
            ('recorded_by',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,to=settings.AUTH_USER_MODEL)),
        ],options={'ordering':['-measured_at','-pk']}),
        migrations.AddIndex(model_name='cameraenvironmentreading',index=models.Index(fields=['camera','-measured_at'],name='env_camera_time_idx')),
        migrations.AddConstraint(model_name='cameraenvironmentreading',constraint=models.CheckConstraint(condition=Q(temperature__gte=-80,temperature__lte=80),name='env_temperature_range')),
        migrations.AddConstraint(model_name='cameraenvironmentreading',constraint=models.CheckConstraint(condition=Q(humidity__gte=0,humidity__lte=100),name='env_humidity_range')),
    ]
