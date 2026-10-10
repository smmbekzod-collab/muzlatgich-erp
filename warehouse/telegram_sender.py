"""Telegram alert delivery with bounded retries; never log bot token or response body."""
import json
import os
import urllib.error
import urllib.request
from datetime import timedelta
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from .models import CameraEnvironmentAlert,TelegramAlertDestination


def send_message(token,chat_id,text):
    """Raises a sanitized error; tests mock this method and never call Telegram."""
    if not token or not chat_id:raise ValueError('Bot token yoki chat ID kiritilmagan')
    if not (token.count(':')==1 and token.split(':',1)[0].isdigit()):
        raise ValueError('Bot token formati noto‘g‘ri')
    req=urllib.request.Request(
        f'https://api.telegram.org/bot{token}/sendMessage',
        data=json.dumps({'chat_id':chat_id,'text':text,
                         'disable_web_page_preview':True},ensure_ascii=False).encode('utf-8'),
        headers={'Content-Type':'application/json; charset=utf-8'},method='POST')
    try:
        with urllib.request.urlopen(req,timeout=8) as resp:
            payload=json.loads(resp.read(2048).decode('utf-8'))
            if resp.status!=200 or payload.get('ok') is not True:
                raise RuntimeError('Telegram API javobi muvaffaqiyatsiz')
    except urllib.error.HTTPError as err:
        # Never include the full URL or response text; that can expose the token.
        raise RuntimeError(f'Telegram HTTP {err.code}') from None
    except (urllib.error.URLError,TimeoutError):
        raise RuntimeError('Telegram ulanishi uzildi') from None


def make_message(alert):
    cam=alert.camera
    location=cam.facility.name if cam.facility_id else 'Asosiy ombor'
    return (
        f'⚠️ MUZLATGICH ERP — kamera ogohlantirishi\n'
        f'Tashkilot: {cam.organization.name}\n'
        f'Filial: {location}\n'
        f'Kamera: №{cam.number}\n'
        f'Hodisa: {alert.get_kind_display()}\n'
        f'Sabab: {alert.description}\n'
        f'Boshlangan vaqt: {timezone.localtime(alert.opened_at):%d.%m.%Y %H:%M}\n'
        'Eslatma: bu qo‘lda kiritilgan kuzatuv va tashkilot me’yorlari asosida.'
    )[:1800]


def drain_alerts(limit=30,now=None):
    now=now or timezone.now()
    token=os.environ.get('TELEGRAM_BOT_TOKEN','').strip()
    if not token:
        return {'sent':0,'failed':0,'skipped':True}
    sent=failed=0
    for _ in range(min(limit,100)):
        with transaction.atomic():
            chosen=(CameraEnvironmentAlert.objects.select_for_update(skip_locked=True)
                .filter(Q(delivery_status__in=['pending','failed'])|
                        Q(delivery_status='sending',claimed_at__lte=now-timedelta(minutes=3)))
                .filter(Q(next_attempt_at__lte=now)|Q(next_attempt_at__isnull=True))
                .filter(attempts__lt=5)
                .select_related('camera__organization','camera__facility')
                .order_by('opened_at','pk').first())
            if chosen is None:break
            chosen.delivery_status='sending'
            chosen.claimed_at=now
            chosen.attempts+=1
            chosen.save(update_fields=['delivery_status','claimed_at','attempts'])
            pk=chosen.pk
        channel=TelegramAlertDestination.objects.filter(
            organization_id=chosen.camera.organization_id,enabled=True).first()
        if not channel:
            CameraEnvironmentAlert.objects.filter(pk=pk,delivery_status='sending').update(
                delivery_status='disabled',claimed_at=None,last_error='Chat o‘chirilgan')
            continue
        try:
            send_message(token,channel.chat_id,make_message(chosen))
        except (RuntimeError,ValueError) as ex:
            failed+=1
            # Exponential backoff; last error contains only our sanitized message.
            CameraEnvironmentAlert.objects.filter(pk=pk,delivery_status='sending').update(
                delivery_status='failed',claimed_at=None,
                next_attempt_at=now+timedelta(minutes=min(60,2**chosen.attempts)),
                last_error=str(ex)[:120])
        else:
            sent+=1
            CameraEnvironmentAlert.objects.filter(pk=pk,delivery_status='sending').update(
                delivery_status='sent',claimed_at=None,next_attempt_at=None,
                sent_at=timezone.now(),last_error='')
    return {'sent':sent,'failed':failed,'skipped':False}
