import django.db.models.deletion
from django.conf import settings
from django.db import migrations,models
from django.db.models import Q

class Migration(migrations.Migration):
    dependencies=[
        ('warehouse','0008_three_daily_report_slots'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations=[
        migrations.CreateModel(name='PlatformNotificationControl',fields=[
            ('id',models.PositiveSmallIntegerField(default=1,editable=False,primary_key=True,serialize=False)),
            ('reports_enabled',models.BooleanField(default=True,verbose_name='08:00 / 14:00 / 20:00 hisobotlar')),
            ('alerts_enabled',models.BooleanField(default=True,verbose_name='Kamera ogohlantirishlari')),
            ('updated_at',models.DateTimeField(auto_now=True)),
            ('updated_by',models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.PROTECT,related_name='+',to=settings.AUTH_USER_MODEL)),
        ]),
        migrations.AddConstraint(model_name='platformnotificationcontrol',
            constraint=models.CheckConstraint(condition=Q(id=1),name='platform_notification_singleton')),
    ]
