import django.db.models.deletion
from django.conf import settings
from django.db import migrations,models
from django.db.models import Q
import django.utils.timezone

class Migration(migrations.Migration):
    dependencies=[('warehouse','0005_camera_environment'),migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations=[
      migrations.CreateModel(name='TelegramAlertDestination',fields=[
        ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),
        ('chat_id',models.CharField(max_length=32,verbose_name='Telegram chat ID')),
        ('enabled',models.BooleanField(default=False,verbose_name='Ogohlantirishlarga ruxsat')),
        ('updated_at',models.DateTimeField(auto_now=True)),
        ('organization',models.OneToOneField(on_delete=django.db.models.deletion.PROTECT,related_name='telegram_alerts',to='core.organization')),
        ('updated_by',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,to=settings.AUTH_USER_MODEL)),
      ]),
      migrations.CreateModel(name='CameraEnvironmentAlert',fields=[
        ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),
        ('kind',models.CharField(choices=[
            ('temp_low','Past harorat'),('temp_high','Yuqori harorat'),
            ('humidity_low','Past namlik'),('humidity_high','Yuqori namlik'),
            ('stale','O‘lchov eskirgan'),('age','Saqlash nazorat kunidan oshgan')],max_length=20,verbose_name='Hodisa')),
        ('description',models.CharField(max_length=300,verbose_name='Sabab')),
        ('opened_at',models.DateTimeField(default=django.utils.timezone.now,verbose_name='Boshlandi')),
        ('resolved_at',models.DateTimeField(blank=True,null=True,verbose_name='Bartaraf etildi')),
        ('delivery_status',models.CharField(choices=[
            ('disabled','Ulanmagan'),('pending','Navbatda'),('sending','Yuborilmoqda'),
            ('sent','Yuborilgan'),('failed','Xatolik')],default='disabled',max_length=15,verbose_name='Telegram holati')),
        ('attempts',models.PositiveSmallIntegerField(default=0)),
        ('next_attempt_at',models.DateTimeField(blank=True,null=True)),
        ('claimed_at',models.DateTimeField(blank=True,null=True)),
        ('sent_at',models.DateTimeField(blank=True,null=True)),
        ('last_error',models.CharField(blank=True,max_length=120)),
        ('camera',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name='environment_alerts',to='core.camera')),
      ],options={'ordering':['-opened_at','-pk']}),
      migrations.AddConstraint(model_name='cameraenvironmentalert',
          constraint=models.UniqueConstraint(condition=Q(resolved_at__isnull=True),
              fields=['camera','kind'],name='unique_open_environment_alert')),
      migrations.AddIndex(model_name='cameraenvironmentalert',
          index=models.Index(fields=['delivery_status','next_attempt_at'],name='env_alert_delivery_idx')),
    ]
