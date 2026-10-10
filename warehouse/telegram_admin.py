"""Platform Super Admin configures a separate Telegram group/chat for each organization.

The Bot API token lives only in Railway environment variables; NEVER store token in DB.
"""
import os
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction,IntegrityError
from django.db.models import Q
from django.shortcuts import redirect,render
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from core.models import Organization
from .models import TelegramAlertDestination,CameraEnvironmentAlert,DailyTelegramDigest
from .notification_controls import current_controls,set_enabled


class TelegramDestinationForm(forms.Form):
    organization=forms.ModelChoiceField(label='Tashkilot',
        queryset=Organization.objects.none(),empty_label='Tashkilotni tanlang')
    chat_id=forms.RegexField(label='Telegram chat ID',regex=r'^-?\d{1,30}$',max_length=32,
        widget=forms.TextInput(attrs={'inputmode':'text','placeholder':'-1001234567890'}),
        help_text='Bot qo‘shilgan shaxsiy chat yoki guruhning haqiqiy raqamli chat ID qiymati.')
    enabled=forms.BooleanField(label='Ogohlantirishlarni yoqish',required=False)
    daily_digest_enabled=forms.BooleanField(label='08:00, 14:00, 20:00 — umumiy hisobotlar',required=False,initial=True)

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['organization'].queryset=Organization.objects.filter(is_active=True).order_by('name')

    def clean(self):
        values=super().clean()
        org=values.get('organization')
        chat=values.get('chat_id')
        if values.get('enabled') and org and chat and TelegramAlertDestination.objects.filter(
            chat_id=chat,enabled=True).exclude(organization=org).exists():
            self.add_error('chat_id','Bu Telegram guruhi boshqa faol tashkilotga tegishli.')
        return values



@login_required
@require_http_methods(['GET','POST'])
def telegram_destinations(request):
    if not request.user.is_active or not request.user.is_superuser:
        raise PermissionDenied('Telegram manzillarini faqat platforma Super Admini o‘zgartiradi.')
    action=request.POST.get('action','') if request.method=='POST' else ''
    if action in ('pause_reports','resume_reports','pause_alerts','resume_alerts'):
        kind='reports' if action.endswith('reports') else 'alerts'
        value=action.startswith('resume')
        set_enabled(kind,value,request.user)
        messages.success(request,
            f'{"Uch mahal hisobotlar" if kind=="reports" else "Kamera ogohlantirishlari"} '
            f'{"yoqildi" if value else "vaqtincha to‘xtatildi"}.')
        return redirect('telegram_destinations')
    if action=='toggle_org_reports':
        org_id=request.POST.get('organization_id','')
        if not org_id.isdecimal():
            raise PermissionDenied('Noto‘g‘ri tashkilot raqami')
        with transaction.atomic():
            route=TelegramAlertDestination.objects.select_for_update().filter(
                organization_id=int(org_id)).first()
            if route is None:
                raise PermissionDenied('Tashkilotning Telegram manzili topilmadi')
            route.daily_digest_enabled=not route.daily_digest_enabled
            route.updated_by=request.user
            route.save(update_fields=['daily_digest_enabled','updated_by','updated_at'])
            if not route.daily_digest_enabled:
                DailyTelegramDigest.objects.filter(organization_id=route.organization_id,
                    delivery_status__in=['pending','failed']).update(
                    delivery_status='disabled',claimed_at=None,next_attempt_at=None,
                    last_error='Tashkilot hisobotlari o‘chirilgan')
        messages.success(request,f'{route.organization.name} uchun hisobotlar ' +
                         ('yoqildi' if route.daily_digest_enabled else 'o‘chirildi'))
        return redirect('telegram_destinations')
    form=TelegramDestinationForm(request.POST if request.method=='POST' else None)
    if request.method=='POST' and form.is_valid():
        data=form.cleaned_data
        try:
            with transaction.atomic():
                Organization.objects.select_for_update().get(pk=data['organization'].pk)
                destination,created=TelegramAlertDestination.objects.update_or_create(
                    organization=data['organization'],
                    defaults={
                        'chat_id':data['chat_id'],'enabled':data['enabled'],
                        'daily_digest_enabled':data['daily_digest_enabled'],'updated_by':request.user})
                destination.full_clean()
                active=CameraEnvironmentAlert.objects.filter(
                    camera__organization=data['organization'],resolved_at__isnull=True)
                if data['enabled']:
                    active.filter(delivery_status='disabled',sent_at__isnull=True).update(
                        delivery_status='pending',next_attempt_at=None,last_error='')
                else:
                    active.filter(delivery_status__in=['pending','failed']).update(
                        delivery_status='disabled',next_attempt_at=None,last_error='Chat o‘chirilgan')
                if not data['enabled'] or not data['daily_digest_enabled']:
                    DailyTelegramDigest.objects.filter(
                        organization=data['organization'],delivery_status__in=['pending','failed']
                    ).update(delivery_status='disabled',next_attempt_at=None,
                             last_error='Hisobotlar o‘chirilgan')
        except IntegrityError:
            form.add_error('chat_id','Bu Telegram guruhidan boshqa faol tashkilot foydalanmoqda.')
        else:
            messages.success(request,'Telegram manzili va uch mahal hisobot jadvali saqlandi.')
            return redirect('telegram_destinations')
    destinations=list(TelegramAlertDestination.objects.select_related(
        'organization','updated_by').order_by('organization__name')[:150])
    return render(request,'warehouse/telegram_admin.html',{
        'today':timezone.localdate(),'form':form,'destinations':destinations,
        'notification_controls':current_controls(),
        'bot_ready':bool(os.environ.get('TELEGRAM_BOT_TOKEN','').strip() or
                         os.environ.get('TELEGRAM_BOT_CONFIGURED','') == '1'),
        'configured_count':TelegramAlertDestination.objects.filter(enabled=True).count(),
        'pending_count':CameraEnvironmentAlert.objects.filter(delivery_status__in=['pending','failed']).count(),
        'digest_pending_count':DailyTelegramDigest.objects.filter(delivery_status__in=['pending','failed']).count(),
    })
