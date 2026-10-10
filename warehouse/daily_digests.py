"""Three tenant-isolated reports daily at 08:00, 14:00, 20:00 Asia/Tashkent.

The database key (organization, local date, slot hour) prevents scheduled reruns
from creating extra reports. Telegram may occasionally deliver twice if a worker
dies after the API accepts a message but before the 'sent' update.
"""
import os
import time as sleeper
from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo
from django.db import transaction
from django.db.models import Count, Sum, Q
from django.utils import timezone
from django.db.models.functions import Coalesce

from .models import (
    Lot, Operation, CameraRentalInvoice, CameraRentalPayment, CameraEnvironmentAlert,
    TelegramAlertDestination, DailyTelegramDigest,
)
from core.models import Organization
from .telegram_sender import send_message
from .notification_controls import is_enabled

UZ_TZ=ZoneInfo('Asia/Tashkent')
SLOTS=(8,14,20)
ZERO=Decimal('0.00')


def local_stamp(value):
    return timezone.localtime(value,UZ_TZ)


def summary_window(local_date,slot_hour):
    if slot_hour not in SLOTS:
        raise ValueError('Ruxsat etilgan hisobot soatlari: 08, 14, 20')
    previous_slot={8:(local_date-timedelta(days=1),20),14:(local_date,8),20:(local_date,14)}
    date,hour=previous_slot[slot_hour]
    return datetime.combine(date,time(hour=hour),tzinfo=UZ_TZ)


def pretty(value):
    return f'{int(value or 0):,}'.replace(',', ' ')


def kg(value):
    return pretty(round(value or ZERO,0))


def compose_organization_report(org, report_date, slot_hour, now=None):
    """Only organization-filtered DB queries; never use a global financial report."""
    now=now or timezone.now()
    start=summary_window(report_date,slot_hour)
    active_lots=Lot.objects.filter(organization=org,closed_on__isnull=True)
    inventory=active_lots.aggregate(
        lot_count=Count('pk'),boxes=Sum('boxes'),
        gross=Sum('gross'),tare=Sum('tare'))
    stock_net=(inventory['gross'] or ZERO)-(inventory['tare'] or ZERO)
    operations=Operation.objects.filter(lot__organization=org)
    recent=operations.filter(created_at__gte=start,created_at__lte=now)
    def movement(kind):
        x=recent.filter(kind=kind).aggregate(
            count=Count('pk'),boxes=Sum('boxes'),gross=Sum('gross'),tare=Sum('tare'))
        return x['count'],x['boxes'] or 0,(x['gross'] or ZERO)-(x['tare'] or ZERO)
    received=movement('receive')
    dispatched=movement('dispatch')
    money_received=recent.aggregate(paid=Sum('payment'))['paid'] or ZERO
    rent_received=CameraRentalPayment.objects.filter(
        invoice__agreement__camera__organization=org,
        created_at__gte=start,created_at__lte=now).aggregate(
        paid=Sum('amount'))['paid'] or ZERO
    exp=recent.aggregate(charged=Sum('charge'))['charged'] or ZERO
    rent_invoice_total=CameraRentalInvoice.objects.filter(
        agreement__camera__organization=org).aggregate(
        amount=Sum('amount'))['amount'] or ZERO
    rent_paid_total=CameraRentalPayment.objects.filter(
        invoice__agreement__camera__organization=org).aggregate(
        amount=Sum('amount'))['amount'] or ZERO
    rent_debt=max(ZERO,rent_invoice_total-rent_paid_total)

    lot_debt=ZERO
    # Grouped DB query; only two numbers per lot, without loading any customers.
    for charged,paid in operations.values('lot_id').annotate(
        total_charge=Sum('charge'),total_paid=Sum('payment')
    ).values_list('total_charge','total_paid').iterator(chunk_size=500):
        lot_debt+=max(ZERO,(charged or ZERO)-(paid or ZERO))
    attention=CameraEnvironmentAlert.objects.filter(
        camera__organization=org,resolved_at__isnull=True,
        camera__is_active=True).select_related('camera','camera__facility').order_by('-opened_at','-pk')
    warning_count=attention.count()
    warning_lines=[]
    for alert in attention[:4]:
        facility=alert.camera.facility.name if alert.camera.facility_id else 'Asosiy'
        warning_lines.append(f'  • {facility} / №{alert.camera.number}: {alert.get_kind_display()}')
    if warning_count>4:
        warning_lines.append(f'  • ... yana {warning_count-4} ta')
    header='🧪 TEST MA’LUMOTLARI\n' if org.name.startswith('TEST') else ''
    text=(
        f'{header}📊 MUZLATGICH ERP — {slot_hour:02d}:00 HISOBOT\n'
        f'🏢 {org.name}\n'
        f'📆 {report_date:%d.%m.%Y} | Toshkent vaqti\n'
        f'🕒 Hisobot oralig‘i: {start:%d.%m %H:%M} — {local_stamp(now):%d.%m %H:%M}\n\n'
        f'📦 OMBOR QOLDIG‘I\n'
        f'• Faol partiyalar: {pretty(inventory["lot_count"])} ta\n'
        f'• Qolgan yashiklar: {pretty(inventory["boxes"])} ta\n'
        f'• Sof vazn: {kg(stock_net)} kg\n'
        f'• Kameralar: {pretty(org.cameras.filter(is_active=True).count())} ta, '
        f'bandi: {pretty(active_lots.values("camera_id").distinct().count())} ta\n\n'
        f'🚚 SO‘NGGI ORALIQ HARAKATI\n'
        f'• Kirim: {pretty(received[0])} ta, {pretty(received[1])} yashik, {kg(received[2])} kg\n'
        f'• Chiqim: {pretty(dispatched[0])} ta, {pretty(dispatched[1])} yashik, {kg(dispatched[2])} kg\n\n'
        f'💰 MOLIYA\n'
        f'• Davrda hisoblangan xizmat: {pretty(exp)} so‘m\n'
        f'• Davrda olingan to‘lov: {pretty(money_received+rent_received)} so‘m\n'
        f'• Yuklar bo‘yicha mavjud qarz: {pretty(lot_debt)} so‘m\n'
        f'• Kamera ijarasi bo‘yicha qarz: {pretty(rent_debt)} so‘m\n'
        f'• Jami qarz: {pretty(lot_debt+rent_debt)} so‘m\n\n'
        f'🌡 KAMERA NAZORATI\n'
        f'• Faol ogohlantirishlar: {warning_count} ta\n'
    )
    text+='\n'.join(warning_lines) if warning_lines else '• Faol ogohlantirish qayd etilmagan'
    text+=(
        '\n\nℹ️ Ko‘rsatkichlar bazadagi oxirgi qaydlar asosida. '
        'Harorat datchikdan real vaqtda olinmaydi. '
        'Ijaraning kelgusi oy to‘lovi qarzga kiritilmagan.'
    )
    return text[:3700]


def enqueue_slot(slot_hour, now=None, organization_code=None):
    """Only insert for enabled, active routes; no duplicate org/date/slot."""
    now=now or timezone.now()
    local=local_stamp(now)
    if not is_enabled('reports'):
        return 0
    if slot_hour not in SLOTS:
        raise ValueError('Noto‘g‘ri hisobot vaqti')
    if local.hour != slot_hour:
        raise ValueError('Faqat rejalashtirilgan mahalliy soatda hisobot yuboriladi')
    routes=TelegramAlertDestination.objects.filter(
        enabled=True,daily_digest_enabled=True,organization__is_active=True
    ).select_related('organization').order_by('organization_id')
    if organization_code:
        routes=routes.filter(organization__code=organization_code)
    made=0
    for route in routes.iterator(chunk_size=100):
        with transaction.atomic():
            Organization.objects.select_for_update().get(pk=route.organization_id)
            if DailyTelegramDigest.objects.filter(
                    organization_id=route.organization_id,report_date=local.date(),
                    slot_hour=slot_hour).exists():
                continue
            msg=compose_organization_report(route.organization,local.date(),slot_hour,now)
            obj,created=DailyTelegramDigest.objects.get_or_create(
                organization=route.organization,report_date=local.date(),slot_hour=slot_hour,
                defaults={'message':msg,'chat_id':route.chat_id,'delivery_status':'pending'})
            if created:made+=1
    return made


def drain_digests(limit=100,now=None,token=None):
    """Same bot serves many chats. Unique route per chat prevents tenant mixing."""
    now=now or timezone.now()
    token=token if token is not None else os.environ.get('TELEGRAM_BOT_TOKEN','').strip()
    if not token or not is_enabled('reports'):
        return {'sent':0,'failed':0,'skipped':True}
    sent=failed=0
    from django.db.models import Q
    for _ in range(max(0,min(limit,500))):
        if not is_enabled('reports'):
            break
        with transaction.atomic():
            digest=(DailyTelegramDigest.objects.select_for_update(skip_locked=True)
                .filter(organization__is_active=True,attempts__lt=5)
                .filter(Q(delivery_status__in=['pending','failed']) |
                    Q(delivery_status='sending',claimed_at__lte=now-timedelta(minutes=3)))
                .filter(Q(next_attempt_at__isnull=True)|Q(next_attempt_at__lte=now))
                .order_by('report_date','slot_hour','pk').first())
            if not digest:break
            digest.delivery_status='sending'
            digest.claimed_at=now
            digest.attempts+=1
            digest.save(update_fields=['delivery_status','claimed_at','attempts'])
        route=TelegramAlertDestination.objects.filter(
            organization_id=digest.organization_id,enabled=True,daily_digest_enabled=True,
            organization__is_active=True,chat_id=digest.chat_id).first()
        if not route:
            DailyTelegramDigest.objects.filter(pk=digest.pk,delivery_status='sending').update(
                delivery_status='disabled',claimed_at=None,last_error='Yo‘nalish o‘zgargan yoki o‘chirilgan')
            continue
        if not is_enabled('reports'):
            DailyTelegramDigest.objects.filter(pk=digest.pk,delivery_status='sending').update(
                delivery_status='disabled',claimed_at=None,last_error='Hisobotlar vaqtincha to‘xtatilgan')
            continue
        try:
            send_message(token,digest.chat_id,digest.message)
        except (RuntimeError,ValueError) as exc:
            failed+=1
            DailyTelegramDigest.objects.filter(pk=digest.pk,delivery_status='sending').update(
                delivery_status='failed',claimed_at=None,
                next_attempt_at=now+timedelta(minutes=min(60,2**digest.attempts)),
                last_error=str(exc)[:120])
        else:
            sent+=1
            DailyTelegramDigest.objects.filter(pk=digest.pk,delivery_status='sending').update(
                delivery_status='sent',sent_at=timezone.now(),claimed_at=None,
                next_attempt_at=None,last_error='')
        # Telegram's general broadcast limits: throttle sustained bursts.
        sleeper.sleep(0.06)
    return {'sent':sent,'failed':failed,'skipped':False}
