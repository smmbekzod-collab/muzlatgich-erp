"""Super-admin announcements with explicit preview and at-most-once send claims."""
import os
import uuid
from functools import wraps

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from .models import TelegramAlertDestination, TelegramAnnouncement, TelegramAnnouncementDelivery
from .telegram_sender import send_message

SALT = 'telegram-announcement-preview-v1'
HEADER = '📣 MUZLATGICH ERP — TIZIM YANGILIKLARI\n\n'


def superadmin(view):
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_active or not request.user.is_superuser:
            raise PermissionDenied('Bu bo‘lim faqat Super Admin uchun.')
        return view(request, *args, **kwargs)
    return wrapped


def active_routes():
    return TelegramAlertDestination.objects.filter(
        enabled=True, organization__is_active=True).select_related('organization').order_by('organization__name')


class RouteChoice(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        return f'{obj.organization.name} · {obj.chat_id}'


class AnnouncementForm(forms.Form):
    body = forms.CharField(label='Yangilik matni', max_length=3000,
        widget=forms.Textarea(attrs={'rows': 8, 'placeholder': 'Yangi imkoniyatlar va foydalanish bo‘yicha yangiliklarni yozing…'}))
    destinations = RouteChoice(label='Qaysi guruhlarga yuborilsin?',
        queryset=TelegramAlertDestination.objects.none(), widget=forms.CheckboxSelectMultiple)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['destinations'].queryset = active_routes()

    def clean_body(self):
        text = self.cleaned_data['body']
        # Telegram counts UTF-16 code units; supplementary emoji take two.
        if len((HEADER + text).encode('utf-16-le')) // 2 > 4096:
            raise forms.ValidationError('Matn juda uzun. Belgilar yoki emojilar sonini kamaytiring.')
        return text


@superadmin
@require_http_methods(['GET', 'POST'])
def announcement_list(request):
    form = AnnouncementForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and request.POST.get('action') == 'confirm':
        try:
            payload = signing.loads(request.POST.get('preview', ''), salt=SALT, max_age=1800)
            if payload['user'] != request.user.pk:
                raise signing.BadSignature()
        except (signing.BadSignature, KeyError, TypeError):
            messages.error(request, 'Ko‘rib chiqish muddati tugagan. Xabarni qayta tayyorlang.')
            return redirect('telegram_announcements')
        with transaction.atomic():
            existing = TelegramAnnouncement.objects.filter(pk=payload['id']).first()
            if existing:
                return redirect('telegram_announcement', pk=existing.pk)
            routes = list(active_routes().select_for_update().filter(pk__in=[r['id'] for r in payload['routes']]))
            snapshot = {r['id']: r['chat_id'] for r in payload['routes']}
            if len(routes) != len(snapshot) or any(snapshot[r.pk] != r.chat_id for r in routes):
                messages.error(request, 'Guruh sozlamalari o‘zgargan. Xabarni qayta ko‘rib chiqing.')
                return redirect('telegram_announcements')
            # A second confirmation may have waited for the same route locks.
            item, created = TelegramAnnouncement.objects.get_or_create(pk=payload['id'],
                defaults={'body': payload['body'], 'created_by': request.user})
            if created:
                TelegramAnnouncementDelivery.objects.bulk_create([
                    TelegramAnnouncementDelivery(announcement=item, destination=r,
                        organization_name=r.organization.name, chat_id=r.chat_id) for r in routes])
        return redirect(reverse('telegram_announcement', kwargs={'pk': item.pk}) + '?send=1')
    if request.method == 'POST' and form.is_valid():
        routes = list(form.cleaned_data['destinations'])
        payload = {'id': str(uuid.uuid4()), 'user': request.user.pk,
            'body': form.cleaned_data['body'],
            'routes': [{'id': r.pk, 'chat_id': r.chat_id} for r in routes]}
        return render(request, 'warehouse/announcement_preview.html', {
            'today': timezone.localdate(), 'body': HEADER + payload['body'], 'routes': routes,
            'preview': signing.dumps(payload, salt=SALT, compress=True)})
    return render(request, 'warehouse/announcements.html', {
        'today': timezone.localdate(), 'form': form,
        'bot_ready': bool(os.environ.get('TELEGRAM_BOT_TOKEN', '').strip()),
        'history': TelegramAnnouncement.objects.select_related('created_by').prefetch_related('deliveries')[:30]})


@superadmin
@require_http_methods(['GET'])
def announcement_detail(request, pk):
    item = get_object_or_404(TelegramAnnouncement.objects.select_related('created_by'), pk=pk)
    deliveries = list(item.deliveries.all())
    return render(request, 'warehouse/announcement_detail.html', {
        'today': timezone.localdate(), 'item': item, 'body': HEADER + item.body,
        'deliveries': deliveries, 'has_pending': any(d.status == 'pending' for d in deliveries),
        'autostart': request.GET.get('send') == '1'})


def deliver_one(pk):
    """Claim once before the API call. Never automatically retry ambiguous timeouts."""
    with transaction.atomic():
        delivery = TelegramAnnouncementDelivery.objects.select_for_update().select_related('announcement').get(pk=pk)
        if delivery.status != 'pending':
            return delivery.status
        route = TelegramAlertDestination.objects.select_for_update().filter(pk=delivery.destination_id).first()
        if not route or not route.enabled or not route.organization.is_active or route.chat_id != delivery.chat_id:
            delivery.status = 'cancelled'
            delivery.last_error = 'Guruh o‘chirilgan yoki manzili o‘zgargan. Yangi xabar tayyorlang.'
        elif not os.environ.get('TELEGRAM_BOT_TOKEN', '').strip():
            delivery.status = 'failed'
            delivery.last_error = 'Bot tokeni sozlanmagan.'
        else:
            delivery.status = 'sending'
        delivery.save(update_fields=['status', 'last_error'])
    if delivery.status != 'sending':
        return delivery.status
    try:
        send_message(os.environ['TELEGRAM_BOT_TOKEN'].strip(), delivery.chat_id, HEADER + delivery.announcement.body)
    except Exception:
        # The response may be lost after delivery. Do not leak tokens or blindly retry.
        TelegramAnnouncementDelivery.objects.filter(pk=pk, status='sending').update(
            status='failed', last_error='Yuborish tasdiqlanmadi. Qayta xabar tuzishdan oldin Telegram guruhini tekshiring.')
        return 'failed'
    TelegramAnnouncementDelivery.objects.filter(pk=pk, status='sending').update(status='sent', sent_at=timezone.now())
    return 'sent'


@superadmin
@require_POST
def announcement_send(request, pk):
    item = get_object_or_404(TelegramAnnouncement, pk=pk)
    delivery = item.deliveries.filter(status='pending').order_by('pk').first()
    status = deliver_one(delivery.pk) if delivery else 'complete'
    remaining = item.deliveries.filter(status='pending').count()
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'status': status, 'remaining': remaining})
    messages.info(request, 'Yuborish natijasi quyidagi ro‘yxatda ko‘rsatilgan.')
    return redirect('telegram_announcement', pk=pk)
