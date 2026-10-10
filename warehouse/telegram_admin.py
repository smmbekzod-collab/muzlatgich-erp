"""Platform Super Admin configures a separate Telegram group/chat for each organization.

The Bot API token lives only in Railway environment variables; NEVER store token in DB.
"""
import os
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import redirect,render
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from core.models import Organization
from .models import TelegramAlertDestination,CameraEnvironmentAlert


class TelegramDestinationForm(forms.Form):
    organization=forms.ModelChoiceField(label='Tashkilot',
        queryset=Organization.objects.none(),empty_label='Tashkilotni tanlang')
    chat_id=forms.RegexField(label='Telegram chat ID',regex=r'^-?\d{1,30}$',max_length=32,
        widget=forms.TextInput(attrs={'inputmode':'text','placeholder':'-1001234567890'}),
        help_text='Bot qo‘shilgan shaxsiy chat yoki guruhning haqiqiy raqamli chat ID qiymati.')
    enabled=forms.BooleanField(label='Ogohlantirishlarni yoqish',required=False)

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['organization'].queryset=Organization.objects.filter(is_active=True).order_by('name')


@login_required
@require_http_methods(['GET','POST'])
def telegram_destinations(request):
    if not request.user.is_active or not request.user.is_superuser:
        raise PermissionDenied('Telegram manzillarini faqat platforma Super Admini o‘zgartiradi.')
    form=TelegramDestinationForm(request.POST if request.method=='POST' else None)
    if request.method=='POST' and form.is_valid():
        data=form.cleaned_data
        with transaction.atomic():
            Organization.objects.select_for_update().get(pk=data['organization'].pk)
            destination,created=TelegramAlertDestination.objects.update_or_create(
                organization=data['organization'],
                defaults={'chat_id':data['chat_id'],'enabled':data['enabled'],'updated_by':request.user})
            destination.full_clean()
        messages.success(request,'Telegram manzili saqlandi. Bot tokeni va davriy ishga tushirish alohida sozlanadi.')
        return redirect('telegram_destinations')
    destinations=list(TelegramAlertDestination.objects.select_related(
        'organization','updated_by').order_by('organization__name')[:150])
    return render(request,'warehouse/telegram_admin.html',{
        'today':timezone.localdate(),'form':form,'destinations':destinations,
        'bot_ready':bool(os.environ.get('TELEGRAM_BOT_TOKEN','').strip() or
                         os.environ.get('TELEGRAM_BOT_CONFIGURED','') == '1'),
        'configured_count':TelegramAlertDestination.objects.filter(enabled=True).count(),
        'pending_count':CameraEnvironmentAlert.objects.filter(delivery_status__in=['pending','failed']).count(),
    })
