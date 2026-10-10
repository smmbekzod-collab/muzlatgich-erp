"""Platform-only onboarding: organization -> branch -> camera.

No implicit demo/test records: all creations follow explicit POST by Super Admin.
The camera's organization is taken from its validated Facility, never user input.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.shortcuts import redirect, render
from django.utils import timezone
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from .models import Organization, Facility, Camera
from .onboarding_forms import OrganizationSetupForm, FacilitySetupForm, CameraSetupForm


def _add_errors(form, exc):
    if isinstance(exc, ValidationError):
        for text in exc.messages:
            form.add_error(None, text)
    else:
        form.add_error(None, 'Ma’lumot allaqachon mavjud yoki boshqa cheklovga zid.')


@login_required
@require_http_methods(['GET', 'POST'])
def platform_dashboard(request):
    if not request.user.is_active or not request.user.is_superuser:
        raise PermissionDenied('Faqat Platforma Super Admini kirishi mumkin.')

    action = request.POST.get('action', '') if request.method == 'POST' else ''
    org_form = OrganizationSetupForm(request.POST if action == 'organization' else None, prefix='org')
    branch_form = FacilitySetupForm(request.POST if action == 'facility' else None, prefix='branch')
    camera_form = CameraSetupForm(request.POST if action == 'camera' else None, prefix='cam')

    if request.method == 'POST':
        handlers = {
            'organization': (org_form, 'Tashkilot qo‘shildi.', 'organizations'),
            'facility': (branch_form, 'Filial qo‘shildi.', 'facilities'),
            'camera': (camera_form, 'Kamera qo‘shildi.', 'cameras')
        }
        selected = handlers.get(action)
        if selected is None:
            raise PermissionDenied('Noma’lum amal.')
        form, notice, anchor = selected
        if form.is_valid():
            try:
                with transaction.atomic():
                    if action == 'organization':
                        org = form.save()
                    elif action == 'facility':
                        branch = form.save()
                    else:
                        values = form.cleaned_data
                        branch = Facility.objects.select_related('organization').get(
                            pk=values['facility'].pk, is_active=True,
                            organization__is_active=True)
                        # Never accept tenant IDs submitted separately from the branch.
                        Camera(
                            organization=branch.organization,
                            facility=branch,
                            number=values['number'],
                            name=values['name'],
                            capacity_kg=values['capacity_kg'],
                        ).save()
            except (ValidationError, IntegrityError) as error:
                _add_errors(form, error)
            else:
                messages.success(request, notice)
                return redirect(reverse('platform_dashboard') + '#' + anchor)

    q = request.GET.get('q', '').strip()[:100]
    orgs = Organization.objects.annotate(
        facility_count=Count('facilities', distinct=True),
        camera_count=Count('cameras', distinct=True),
    ).order_by('name')
    if q:
        orgs = orgs.filter(Q(name__icontains=q) | Q(code__icontains=q))
    # A nationwide SaaS could have thousands of organizations: paginate later.
    # Keep the first 50 in the directory and never retrieve every lot here.
    org_rows = list(orgs[:50])
    facilities = list(
        Facility.objects.select_related('organization').annotate(
            camera_count=Count('cameras')
        ).order_by('-created_at')[:40]
    )

    return render(request, 'warehouse/platform_dashboard.html', {
        'today': timezone.localdate(),
        'organization_form': org_form,
        'facility_form': branch_form,
        'camera_form': camera_form,
        'organizations': org_rows,
        'facility_rows': facilities,
        'q': q,
        'total_organizations': Organization.objects.count(),
        'total_facilities': Facility.objects.count(),
        'total_cameras': Camera.objects.count(),
    })
