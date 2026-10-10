"""Persistent incident detection: no network access or Telegram secret required.

A camera has one open incident per issue. A new abnormal reading opens an
incident; repeat readings do not flood Telegram. Once normal, the incident is
resolved, and the next deviation may open a new incident.

A periodic command is REQUIRED to detect stale measurements and aging goods
without a new manual reading.
"""
from django.db import transaction
from django.db.models import Min
from django.utils import timezone
from core.models import Camera
from .models import (
    CameraEnvironmentPolicy,CameraEnvironmentReading,Lot,
    TelegramAlertDestination,CameraEnvironmentAlert
)
from datetime import timedelta


def camera_issues(policy,reading,oldest,now):
    issues={}
    if policy is None:return issues
    if reading is not None:
        for field,kind,value,label,operator in (
           ('min_temperature','temp_low',reading.temperature,'Harorat pastki chegaradan tushgan',lambda a,b:a<b),
           ('max_temperature','temp_high',reading.temperature,'Harorat yuqori chegaradan oshgan',lambda a,b:a>b),
           ('min_humidity','humidity_low',reading.humidity,'Namlik pastki chegaradan tushgan',lambda a,b:a<b),
           ('max_humidity','humidity_high',reading.humidity,'Namlik yuqori chegaradan oshgan',lambda a,b:a>b),
        ):
            threshold=getattr(policy,field)
            if threshold is not None and operator(value,threshold):
                issues[kind]=f'{label}: {value} (chegara {threshold})'
        if now-reading.measured_at>timedelta(hours=policy.check_interval_hours):
            issues['stale']=f'Oxirgi o‘lchov {policy.check_interval_hours} soatdan eski'
    if oldest is not None and policy.max_storage_days is not None:
        days=max(1,(timezone.localtime(now).date()-oldest).days+1)
        if days>policy.max_storage_days:
            issues['age']=f'Eng eski partiya {days} kun; nazorat chegarasi {policy.max_storage_days} kun'
    return issues


@transaction.atomic
def reconcile_camera(camera_id,now=None):
    """Serialize against other readers/cron workers on the Camera row."""
    now=now or timezone.now()
    camera=Camera.objects.select_for_update().select_related('organization').get(pk=camera_id)
    policy=CameraEnvironmentPolicy.objects.filter(camera=camera).first()
    reading=CameraEnvironmentReading.objects.filter(camera=camera).order_by('-measured_at','-pk').first()
    oldest=Lot.objects.filter(camera=camera,closed_on__isnull=True).aggregate(old=Min('received_on'))['old']
    conditions=(camera_issues(policy,reading,oldest,now) if camera.is_active and camera.organization.is_active
                else {})
    current={a.kind:a for a in CameraEnvironmentAlert.objects.select_for_update().filter(
        camera=camera,resolved_at__isnull=True)}
    channel=TelegramAlertDestination.objects.filter(organization_id=camera.organization_id,enabled=True).first()
    opened=[]
    for kind,reason in conditions.items():
        if kind in current:continue
        alert=CameraEnvironmentAlert.objects.create(camera=camera,kind=kind,description=reason,
            opened_at=now,delivery_status='pending' if channel else 'disabled')
        opened.append(alert)
    for kind,old in current.items():
        if kind not in conditions:
            old.resolved_at=now
            old.save(update_fields=['resolved_at'])
    return opened


def scan_all_cameras(max_cameras=10000):
    """Best run periodically (e.g. every 5 minutes) by one scheduler service."""
    checked=created=0
    for camera_id in Camera.objects.order_by('pk').values_list('pk',flat=True).iterator(chunk_size=250):
        if checked>=max_cameras:break
        checked+=1
        created+=len(reconcile_camera(camera_id))
    return checked,created
