"""Tenant-scoped device enrollment. Never expose gateway secrets after creation."""
import secrets
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.hashers import make_password
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from core import access
from core.models import Membership, Facility
from .iot_models import IoTGateway, IoTDevice


def admin_orgs(user):
    if not user.is_authenticated or not user.is_active:
        return access.organizations(user).none()
    if user.is_superuser:
        return access.organizations(user)
    ids = Membership.objects.filter(user=user,is_active=True,organization__is_active=True,
        role='admin').values_list('organization_id',flat=True)
    return access.organizations(user).filter(pk__in=ids)


class GatewayForm(forms.ModelForm):
    class Meta:
        model=IoTGateway
        fields=['organization','facility','name','transport','offline_minutes']
    def __init__(self,*args,orgs=None,facilities=None,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['organization'].queryset=orgs
        self.fields['facility'].queryset=facilities
    def clean(self):
        clean=super().clean()
        org,site=clean.get('organization'),clean.get('facility')
        if org and site and site.organization_id!=org.pk:
            self.add_error('facility','Ombor boshqa tashkilotga tegishli.')
        return clean


class DeviceForm(forms.ModelForm):
    class Meta:
        model=IoTDevice
        fields=['gateway','camera','transport','code','name','model_name','address']
    def __init__(self,*args,gateways=None,cameras=None,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['gateway'].queryset=gateways
        self.fields['camera'].queryset=cameras
    def clean(self):
        clean=super().clean()
        gw,cam=clean.get('gateway'),clean.get('camera')
        if gw and cam and (gw.organization_id!=cam.organization_id or gw.facility_id!=cam.facility_id):
            self.add_error('camera','Kamera va gateway bir hududda bo‘lishi shart.')
        return clean


@never_cache
@login_required
@require_http_methods(['GET','POST'])
def iot_hub(request):
    visible_cameras=access.cameras(request.user).filter(
        organization__is_active=True, is_active=True).select_related('organization','facility')
    visible_facilities=access.facilities(request.user).filter(organization__is_active=True)
    orgs=admin_orgs(request.user).filter(is_active=True)
    managed_facilities=visible_facilities.filter(organization__in=orgs)
    managed_cameras=visible_cameras.filter(
        organization__in=orgs,facility__in=managed_facilities)
    gateways=IoTGateway.objects.filter(facility__in=visible_facilities,
        organization__in=access.organizations(request.user)).select_related(
        'organization','facility').order_by('organization__name','name')
    managed_gateways=gateways.filter(organization__in=orgs,facility__in=managed_facilities)
    devices=IoTDevice.objects.filter(
        gateway__in=gateways,camera__in=visible_cameras).select_related(
        'gateway','camera','camera__organization','camera__facility').order_by(
        'camera__organization__name','camera__number','code')
    token=None
    action=request.POST.get('action') if request.method=='POST' else None
    gw_form=GatewayForm(request.POST if action=='create_gateway' else None,
        orgs=orgs,facilities=managed_facilities,prefix='gateway')
    device_form=DeviceForm(request.POST if action=='create_device' else None,
        gateways=managed_gateways,cameras=managed_cameras,prefix='device')
    if request.method=='POST':
        if not orgs.exists():
            raise PermissionDenied('IoT qurilmalarni faqat tashkilot admini boshqaradi.')
        if action=='create_gateway' and gw_form.is_valid():
            with transaction.atomic():
                gw=gw_form.save(commit=False)
                gw.created_by=request.user
                secret=secrets.token_urlsafe(40)
                gw.secret_hash=make_password(secret)
                gw.full_clean()
                gw.save()
            token=f'{gw.pk}.{secret}'
            messages.success(request,'Gateway yaratildi. Kalit faqat shu sahifada bir marta ko‘rsatiladi.')
        elif action=='create_device' and device_form.is_valid():
            with transaction.atomic():
                device=device_form.save(commit=False)
                device.full_clean()
                device.save()
            messages.success(request,'Datchik kameraga biriktirildi.')
            return redirect('iot_hub')
        elif action in ('rotate','disable','enable'):
            gw=managed_gateways.filter(pk=request.POST.get('gateway_id')).first()
            if gw is None:
                raise PermissionDenied('Bu gatewayni boshqarish huquqi yo‘q.')
            if action=='rotate':
                secret=secrets.token_urlsafe(40)
                gw.secret_hash=make_password(secret)
                gw.save(update_fields=['secret_hash'])
                token=f'{gw.pk}.{secret}'
                messages.success(request,'Eski gateway kaliti bekor qilindi. Yangisini xavfsiz saqlang.')
            else:
                gw.is_active=action=='enable'
                gw.save(update_fields=['is_active'])
                messages.success(request,'Gateway holati yangilandi.')
        elif action not in ('create_gateway','create_device'):
            raise PermissionDenied('Noma’lum amal.')
    response=render(request,'warehouse/iot_hub.html',{
        'today':timezone.localdate(),'gateways':gateways,
        'devices':devices,'gateway_form':gw_form,'device_form':device_form,
        'new_token':token,'can_manage':orgs.exists(),
        'gateway_count':gateways.count(),'device_count':devices.count(),
    })
    response['Cache-Control']='no-store, private'
    response['Referrer-Policy']='no-referrer'
    return response
