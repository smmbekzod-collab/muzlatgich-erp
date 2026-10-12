"""Cloud HTTPS ingest for an on-site IoT gateway.

This endpoint does NOT talk directly to RS485 or MQTT. The local adapter polls
physical sensors and POSTs signed/authenticated HTTPS JSON to this endpoint.
Duplicate stable event IDs are safely acknowledged without duplicate readings.
"""
import json
from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal, InvalidOperation
from uuid import UUID
from django.contrib.auth.hashers import check_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from .iot_models import IoTGateway, IoTDevice, IoTReceipt
from .models import CameraEnvironmentReading
from .monitor_alerts import reconcile_camera

MAX_BODY_BYTES = 32768
MAX_BATCH = 50


def _error(reason, status):
    response = JsonResponse({'ok': False, 'error': reason}, status=status)
    response['Cache-Control'] = 'no-store'
    return response


def _auth(request):
    value = request.headers.get('Authorization', '')
    if not value.startswith('Bearer ') or len(value) > 256:
        return None
    raw = value[7:]
    if raw.count('.') != 1:
        return None
    id_part, secret = raw.split('.', 1)
    try:
        UUID(id_part)
    except (ValueError, AttributeError):
        return None
    if len(secret) < 32 or len(secret) > 160:
        return None
    gateway = IoTGateway.objects.select_related('organization','facility').filter(
        id=id_part, is_active=True, organization__is_active=True, facility__is_active=True
    ).first()
    if gateway is None or not check_password(secret, gateway.secret_hash):
        return None
    return gateway


def _number(raw, label, low, high):
    if isinstance(raw, bool) or raw is None:
        raise ValueError(f'{label} son bo‘lishi shart')
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f'{label} noto‘g‘ri')
    if not value.is_finite() or not low <= value <= high or value.as_tuple().exponent < -2:
        raise ValueError(f'{label} oraliq yoki aniqlik xatosi')
    return value


def _measured(raw, now):
    if not isinstance(raw, str) or len(raw) > 40:
        raise ValueError('measured_at ISO-8601 bo‘lishi shart')
    try:
        value = datetime.fromisoformat(raw.replace('Z', '+00:00'))
    except (ValueError, TypeError):
        raise ValueError('measured_at noto‘g‘ri format')
    if timezone.is_naive(value):
        raise ValueError('measured_at vaqt zonasi ko‘rsatilishi kerak')
    value = value.astimezone(dt_timezone.utc)
    if not now - timedelta(hours=48) <= value <= now + timedelta(minutes=5):
        raise ValueError('O‘lchov vaqti 48 soatdan eski yoki kelajakda')
    return value


@csrf_exempt  # Machine-to-machine endpoint: Bearer token, never browser session.
@require_POST
def iot_readings(request):
    if request.content_type != 'application/json':
        return _error('JSON talab etiladi', 415)
    if len(request.body) > MAX_BODY_BYTES:
        return _error('Paket juda katta', 413)
    gateway = _auth(request)
    if gateway is None:
        return _error('IoT kalit tasdiqlanmadi', 401)
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except (UnicodeError, ValueError):
        return _error('JSON buzilgan', 400)
    if not isinstance(payload, dict):
        return _error('JSON obyekt bo‘lishi kerak', 400)
    items = payload.get('readings')
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_BATCH:
        return _error('1–50 ta o‘lchov yuboring', 400)
    now = timezone.now()
    codes = []
    for item in items:
        if not isinstance(item, dict):
            return _error('O‘lchov obyekt emas', 400)
        codes.append(item.get('device_code'))
    if any(not isinstance(c, str) or len(c) > 64 for c in codes):
        return _error('device_code noto‘g‘ri', 400)
    devices = {
        d.code:d for d in IoTDevice.objects.select_related('camera').filter(
            gateway=gateway, is_active=True, camera__is_active=True,
            camera__organization__is_active=True, camera__facility__is_active=True)
    }
    prepared = []
    for item in items:
        try:
            device = devices.get(item['device_code'])
            if device is None:
                raise ValueError('Qurilma bu gateway/kameraga tegishli emas')
            eid = item.get('event_id')
            if not isinstance(eid, str) or not 1 <= len(eid) <= 80:
                raise ValueError('event_id majburiy, 1–80 belgi')
            prepared.append((
                device, eid,
                _measured(item.get('measured_at'), now),
                _number(item.get('temperature'), 'Harorat', Decimal('-80'), Decimal('80')),
                _number(item.get('humidity'), 'Namlik', Decimal('0'), Decimal('100'))
            ))
        except (KeyError, ValueError) as err:
            return _error(str(err), 400)
    inserted = duplicate = 0
    changed_cameras = set()
    try:
        with transaction.atomic():
            # Serializing on the gateway prevents concurrent workers from writing
            # the same event twice, and makes replay behavior deterministic.
            IoTGateway.objects.select_for_update().get(pk=gateway.pk)
            for device, eid, measured, temp, humid in prepared:
                existing = IoTReceipt.objects.select_related('reading').filter(
                    device=device,event_id=eid).first()
                if existing:
                    old = existing.reading
                    if (old.measured_at, old.temperature, old.humidity) != (measured,temp,humid):
                        raise ValueError('event_id avval boshqa qiymatlar bilan ishlatilgan')
                    duplicate += 1
                    continue
                reading = CameraEnvironmentReading(
                    camera=device.camera, measured_at=measured,temperature=temp,
                    humidity=humid,source='sensor',recorded_by=None,
                    note=f'IoT datchik: {device.code}'[:250])
                reading.save()
                IoTReceipt.objects.create(device=device,event_id=eid,reading=reading)
                IoTDevice.objects.filter(pk=device.pk).update(last_seen_at=now)
                changed_cameras.add(device.camera_id)
                inserted += 1
            IoTGateway.objects.filter(pk=gateway.pk).update(last_seen_at=now)
            for camera_id in changed_cameras:
                transaction.on_commit(lambda camera_id=camera_id: reconcile_camera(camera_id))
    except (ValueError, ValidationError) as err:
        return _error(str(err), 409)
    response = JsonResponse({'ok':True,'inserted':inserted,'duplicates':duplicate})
    response['Cache-Control'] = 'no-store'
    return response
