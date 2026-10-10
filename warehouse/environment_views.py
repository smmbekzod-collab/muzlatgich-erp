"""Mobile-first, tenant-scoped manual temperature and humidity monitoring."""
import csv
from datetime import timedelta
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Min, OuterRef, Subquery
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_GET

from core import access
from core.models import Camera
from .environment_forms import CameraEnvironmentPolicyForm, CameraEnvironmentReadingForm
from .environment_logic import assess_camera
from .models import CameraEnvironmentPolicy, CameraEnvironmentReading, Lot


def _has_permission(user,camera,ability):
    try:
        access.authorize(user,camera.organization_id,camera.pk,ability)
        return True
    except PermissionDenied:
        return False


def _safe_camera(user,camera_id):
    return get_object_or_404(
        access.cameras(user).select_related('organization','facility'),
        pk=camera_id, organization__is_active=True)


@login_required
@require_GET
def monitor_overview(request):
    allowed=access.cameras(request.user).filter(organization__is_active=True).select_related(
        'organization','facility').order_by('organization__name','facility__name','number','pk')
    selected=request.GET.get('organization','')
    if selected:
        if selected.isdecimal():
            allowed=allowed.filter(organization_id=int(selected))
        else:
            allowed=allowed.none()
    choices=access.organizations(request.user).filter(
        pk__in=access.cameras(request.user).values('organization_id'),
        is_active=True).order_by('name')
    # A page of records, not every camera in the republic.
    page=Paginator(allowed,24).get_page(request.GET.get('page',1))
    cams=list(page.object_list)
    ids=[c.pk for c in cams]
    policies={p.camera_id:p for p in CameraEnvironmentPolicy.objects.filter(camera_id__in=ids)}
    latest=CameraEnvironmentReading.objects.filter(camera_id=OuterRef('pk')).order_by(
        '-measured_at','-pk')
    current_ids=list(Camera.objects.filter(pk__in=ids).annotate(last_id=Subquery(
        latest.values('pk')[:1])).values_list('last_id',flat=True))
    readings={r.camera_id:r for r in CameraEnvironmentReading.objects.filter(pk__in=[
        pk for pk in current_ids if pk is not None])}
    oldest={x['camera_id']:x['first'] for x in Lot.objects.filter(
        camera_id__in=ids,closed_on__isnull=True).values('camera_id').annotate(
        first=Min('received_on'))}
    now=timezone.now()
    rows=[assess_camera(c,policies.get(c.pk),readings.get(c.pk),oldest.get(c.pk),now)
          for c in cams]
    warning_count=sum(1 for r in rows if r['issues'])
    return render(request,'warehouse/monitor_overview.html',{
        'today':timezone.localdate(), 'page':page,'rows':rows,
        'organizations':choices,'selected_org':selected,
        'warning_count':warning_count,'camera_count':len(rows),
        'observed_count':sum(bool(r['reading']) for r in rows),
    })


@login_required
@require_http_methods(['GET','POST'])
def monitor_camera(request,camera_id):
    camera=_safe_camera(request.user,camera_id)
    existing=CameraEnvironmentPolicy.objects.filter(camera=camera).first()
    policy=existing or CameraEnvironmentPolicy(camera=camera,updated_by=request.user)
    can_configure=_has_permission(request.user,camera,'tariff')
    can_record=_has_permission(request.user,camera,'environment')
    action=request.POST.get('action') if request.method=='POST' else None

    policy_form=CameraEnvironmentPolicyForm(
        request.POST if action=='policy' else None, instance=policy, prefix='policy')
    reading_form=CameraEnvironmentReadingForm(
        request.POST if action=='reading' else None,prefix='reading')
    if request.method=='POST':
        if action=='policy':
            if not can_configure:raise PermissionDenied('Me’yorlarni faqat tarif boshqarish huquqli admin sozlaydi.')
            if policy_form.is_valid():
                with transaction.atomic():
                    Camera.objects.select_for_update().get(pk=camera.pk)
                    saved=policy_form.save(commit=False)
                    saved.camera=camera
                    saved.updated_by=request.user
                    saved.full_clean()
                    saved.save()
                messages.success(request,'Harorat, namlik va nazorat muddatlari saqlandi.')
                return redirect('monitor_camera',camera_id=camera.pk)
        elif action=='reading':
            if not can_record:raise PermissionDenied('Harorat va namlik qayd etish huquqi yo‘q.')
            if not camera.is_active:raise PermissionDenied('Faol bo‘lmagan kameraga yangi qayd kiritib bo‘lmaydi.')
            if reading_form.is_valid():
                observation=reading_form.save(commit=False)
                observation.camera=camera
                observation.recorded_by=request.user
                observation.source='manual'
                observation.save()
                messages.success(request,'O‘lchov jurnalga saqlandi. Ogohlantirishlar yangilandi.')
                return redirect('monitor_camera',camera_id=camera.pk)
        else:
            raise PermissionDenied('Noma’lum amal.')

    history=list(CameraEnvironmentReading.objects.filter(
        camera=camera).select_related('recorded_by').order_by('-measured_at','-pk')[:35])
    recent=history[0] if history else None
    lots=list(Lot.objects.filter(camera=camera,closed_on__isnull=True)
             .select_related('customer').order_by('received_on','pk')[:50])
    oldest=lots[0].received_on if lots else None
    outcome=assess_camera(camera,existing,recent,oldest)
    for lot in lots:
        lot.current_stay_days=max(1,(timezone.localdate()-lot.received_on).days+1)
        lot.age_warning=bool(existing and existing.max_storage_days is not None
                             and lot.current_stay_days>existing.max_storage_days)
    return render(request,'warehouse/monitor_camera.html',{
        'today':timezone.localdate(),'camera':camera,
        'policy':existing,'policy_form':policy_form,'reading_form':reading_form,
        'can_configure':can_configure,'can_record':can_record,
        'summary':outcome,'history':history,'lots':lots,
    })


@login_required
@require_GET
def monitor_csv(request,camera_id):
    """Read-only, scoped 30-day export: at most 5000 measurements per camera."""
    camera=_safe_camera(request.user,camera_id)
    start=timezone.now()-timedelta(days=30)
    response=HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition']=f'attachment; filename="camera_{camera.pk}_monitor_30_days.csv"'
    response.write('\ufeff')
    writer=csv.writer(response)
    writer.writerow(['Tashkilot','Filial','Kamera','O‘lchangan sana-vaqt',
                     'Harorat (°C)','Namlik (%)','Manba','Qayd qilgan','Izoh'])
    def safe(value):
        string=str(value or '')
        if string.startswith(('=','+','-','@','\t','\r','\n')):
            return "'" + string
        return string
    queryset=(CameraEnvironmentReading.objects.filter(
        camera=camera,measured_at__gte=start).select_related('recorded_by')
        .order_by('-measured_at','-pk')[:5000])
    for x in queryset.iterator(chunk_size=500):
        writer.writerow([
            safe(camera.organization.name),safe(camera.facility.name if camera.facility_id else ''),
            camera.number,timezone.localtime(x.measured_at).strftime('%Y-%m-%d %H:%M:%S'),
            x.temperature,x.humidity,x.get_source_display(),safe(x.recorded_by.username),
            safe(x.note)])
    return response
