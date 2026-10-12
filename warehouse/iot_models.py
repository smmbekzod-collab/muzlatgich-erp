"""Tenant-isolated Universal IoT Hub. Hardware connectors are installed on site.

Only HTTPS gateway ingestion is implemented in v1; Wi-Fi, Modbus, MQTT and
LoRaWAN describe the physical gateway link, not direct cloud integrations.
"""
import uuid
from datetime import timedelta
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone
from core.models import Organization, Facility, Camera


class IoTGateway(models.Model):
    TRANSPORTS = [
        ('rs485', 'RS485 / Modbus orqali mahalliy gateway'),
        ('wifi', 'Wi-Fi / HTTPS'),
        ('mqtt', 'MQTT orqali mahalliy adapter'),
        ('lorawan', 'LoRaWAN orqali adapter'),
        ('other', 'Boshqa adapter'),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name='iot_gateways')
    facility = models.ForeignKey(Facility, on_delete=models.PROTECT, related_name='iot_gateways')
    name = models.CharField(max_length=120)
    transport = models.CharField(max_length=12, choices=TRANSPORTS, default='rs485')
    secret_hash = models.CharField(max_length=160, editable=False)
    is_active = models.BooleanField(default=True)
    offline_minutes = models.PositiveSmallIntegerField(default=15)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['organization_id', 'facility_id', 'name']
        constraints = [
            models.UniqueConstraint(fields=['facility', 'name'], name='iot_gateway_name_site_unique')
        ]

    def clean(self):
        if self.facility_id and self.organization_id and not Facility.objects.filter(
            pk=self.facility_id, organization_id=self.organization_id
        ).exists():
            raise ValidationError({'facility':'Gateway faqat shu tashkilot omboriga ulanadi.'})
        if not 2 <= self.offline_minutes <= 1440:
            raise ValidationError({'offline_minutes':'2–1440 daqiqa oralig‘ini tanlang.'})
        if self.pk and IoTGateway.objects.filter(pk=self.pk).exists():
            previous = IoTGateway.objects.get(pk=self.pk)
            if (previous.organization_id, previous.facility_id) != (self.organization_id, self.facility_id):
                raise ValidationError('Ishlatilayotgan gatewayni boshqa tashkilot yoki hududga ko‘chirmang.')

    def online(self):
        return bool(self.last_seen_at and timezone.now() - self.last_seen_at <= timedelta(minutes=self.offline_minutes))

    def __str__(self):
        return f'{self.organization} / {self.facility} / {self.name}'


class IoTDevice(models.Model):
    gateway = models.ForeignKey(IoTGateway, on_delete=models.PROTECT, related_name='devices')
    camera = models.ForeignKey(Camera, on_delete=models.PROTECT, related_name='iot_devices')
    code = models.SlugField(max_length=64)
    name = models.CharField(max_length=120)
    model_name = models.CharField(max_length=120, blank=True)
    address = models.PositiveSmallIntegerField(null=True, blank=True, help_text='Modbus ID, 1–247')
    is_active = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['gateway_id', 'camera__number', 'code']
        constraints = [
            models.UniqueConstraint(fields=['gateway', 'code'], name='iot_device_code_gateway_unique'),
            models.UniqueConstraint(fields=['gateway', 'address'],
                                    condition=Q(address__isnull=False), name='iot_modbus_address_gateway_unique'),
        ]

    def clean(self):
        if self.gateway_id and self.camera_id:
            if not Camera.objects.filter(pk=self.camera_id,
                organization_id=self.gateway.organization_id,
                facility_id=self.gateway.facility_id).exists():
                raise ValidationError({'camera':'Datchik va gateway bir tashkilot hamda hududga tegishli bo‘lishi shart.'})
        if self.address is not None and not 1 <= self.address <= 247:
            raise ValidationError({'address':'Modbus manzil 1–247 bo‘lishi kerak.'})
        if self.gateway_id and self.gateway.transport == 'rs485' and self.address is None:
            raise ValidationError({'address':'RS485 uchun har bir qurilmaga alohida Modbus manzil belgilang.'})
        if self.pk and IoTDevice.objects.filter(pk=self.pk).exists():
            prev = IoTDevice.objects.get(pk=self.pk)
            if (prev.gateway_id,prev.camera_id) != (self.gateway_id,self.camera_id):
                raise ValidationError('Ulangan datchikni boshqa gateway/kameraga ko‘chirmang; yangisini yarating.')

    def online(self):
        return bool(self.last_seen_at and timezone.now() - self.last_seen_at <=
                    timedelta(minutes=self.gateway.offline_minutes))

    def __str__(self):
        return f'{self.camera} / {self.code}'


class IoTReceipt(models.Model):
    """Unique event_id per device guarantees replay-safe telemetry ingestion."""
    device = models.ForeignKey(IoTDevice, on_delete=models.PROTECT, related_name='receipts')
    event_id = models.CharField(max_length=80)
    reading = models.OneToOneField('warehouse.CameraEnvironmentReading',
        on_delete=models.PROTECT, related_name='iot_receipt')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['device','event_id'], name='iot_receipt_event_unique')
        ]
