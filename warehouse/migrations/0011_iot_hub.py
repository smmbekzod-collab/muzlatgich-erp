import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
from django.db.models import Q

class Migration(migrations.Migration):
    dependencies = [('warehouse', '0010_telegram_announcements'), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.AlterField('cameraenvironmentreading','recorded_by',models.ForeignKey(
            to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.PROTECT, null=True, blank=True)),
        migrations.CreateModel('IoTGateway', fields=[
            ('id',models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False,serialize=False)),
            ('name',models.CharField(max_length=120)),
            ('transport',models.CharField(max_length=12,default='rs485',choices=[
                ('rs485','RS485 / Modbus orqali mahalliy gateway'),('wifi','Wi-Fi / HTTPS'),
                ('mqtt','MQTT orqali mahalliy adapter'),('lorawan','LoRaWAN orqali adapter'),('other','Boshqa adapter')])),
            ('secret_hash',models.CharField(max_length=160,editable=False)),
            ('is_active',models.BooleanField(default=True)),
            ('offline_minutes',models.PositiveSmallIntegerField(default=15)),
            ('last_seen_at',models.DateTimeField(null=True,blank=True)),
            ('created_at',models.DateTimeField(auto_now_add=True)),
            ('organization',models.ForeignKey('core.Organization',on_delete=django.db.models.deletion.PROTECT,related_name='iot_gateways')),
            ('facility',models.ForeignKey('core.Facility',on_delete=django.db.models.deletion.PROTECT,related_name='iot_gateways')),
            ('created_by',models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=django.db.models.deletion.PROTECT)),
        ],options={'ordering':['organization_id','facility_id','name']}),
        migrations.CreateModel('IoTDevice',fields=[
            ('id',models.BigAutoField(primary_key=True,serialize=False,auto_created=True,verbose_name='ID')),
            ('code',models.SlugField(max_length=64)),
            ('name',models.CharField(max_length=120)),
            ('model_name',models.CharField(max_length=120,blank=True)),
            ('address',models.PositiveSmallIntegerField(null=True,blank=True,help_text='Modbus ID, 1–247')),
            ('is_active',models.BooleanField(default=True)),
            ('last_seen_at',models.DateTimeField(null=True,blank=True)),
            ('created_at',models.DateTimeField(auto_now_add=True)),
            ('gateway',models.ForeignKey('warehouse.IoTGateway',on_delete=django.db.models.deletion.PROTECT,related_name='devices')),
            ('camera',models.ForeignKey('core.Camera',on_delete=django.db.models.deletion.PROTECT,related_name='iot_devices')),
        ],options={'ordering':['gateway_id','camera__number','code']}),
        migrations.CreateModel('IoTReceipt',fields=[
            ('id',models.BigAutoField(primary_key=True,serialize=False,auto_created=True,verbose_name='ID')),
            ('event_id',models.CharField(max_length=80)),
            ('created_at',models.DateTimeField(auto_now_add=True)),
            ('device',models.ForeignKey('warehouse.IoTDevice',on_delete=django.db.models.deletion.PROTECT,related_name='receipts')),
            ('reading',models.OneToOneField('warehouse.CameraEnvironmentReading',on_delete=django.db.models.deletion.PROTECT,related_name='iot_receipt')),
        ]),
        migrations.AddConstraint('iotgateway',models.UniqueConstraint(fields=['facility','name'],name='iot_gateway_name_site_unique')),
        migrations.AddConstraint('iotdevice',models.UniqueConstraint(fields=['gateway','code'],name='iot_device_code_gateway_unique')),
        migrations.AddConstraint('iotdevice',models.UniqueConstraint(fields=['gateway','address'],condition=Q(address__isnull=False),name='iot_modbus_address_gateway_unique')),
        migrations.AddConstraint('iotreceipt',models.UniqueConstraint(fields=['device','event_id'],name='iot_receipt_event_unique')),
        migrations.AlterField('cameraenvironmentalert','kind',models.CharField(
            verbose_name='Hodisa',max_length=20,choices=[
                ('temp_low','Past harorat'),('temp_high','Yuqori harorat'),
                ('humidity_low','Past namlik'),('humidity_high','Yuqori namlik'),
                ('stale','O‘lchov eskirgan'),('age','Saqlash nazorat kunidan oshgan'),
                ('sensor_offline','IoT datchik aloqasi uzilgan')
            ])),
    ]
