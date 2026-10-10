"""Only Platform Super Admin may create, scope and revoke employee access."""
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods

from .models import Organization, Facility, Membership
from .staff_forms import StaffSetupForm


# Rights are explicit; labels alone never authorize a backend operation.
ROLE_RIGHTS = {
    'admin': ('can_receive', 'can_dispatch', 'can_transfer', 'can_take_payment',
              'can_view_finance', 'can_set_tariffs', 'can_manage_expenses'),
    'keeper': ('can_receive', 'can_dispatch', 'can_transfer'),
    'accountant': ('can_take_payment', 'can_view_finance', 'can_manage_expenses'),
    'director': ('can_view_finance',),
}
ALL_RIGHTS = (
    'can_receive', 'can_dispatch', 'can_transfer', 'can_take_payment',
    'can_view_finance', 'can_set_tariffs', 'can_dispatch_on_debt', 'can_manage_expenses'
)


@transaction.atomic
def create_employee(data):
    """Creates no organization/camera, never stores or returns a plaintext password."""
    org=Organization.objects.select_for_update().get(
        pk=data['organization'].pk, is_active=True)
    scope=data.get('facility')
    if scope:
        scope=Facility.objects.get(
            pk=scope.pk,organization=org,is_active=True)
    role=data['role']
    if role not in ROLE_RIGHTS:
        raise ValidationError('Noma’lum xodim lavozimi.')
    User=get_user_model()
    if User.objects.filter(username__iexact=data['username']).exists():
        raise ValidationError('Bu login allaqachon band.')
    employee=User.objects.create_user(
        username=data['username'], password=data['password1'],
        first_name=data['first_name'], last_name=data.get('last_name',''),
        is_staff=True, is_active=True)
    grant=Membership(
        user=employee,organization=org,role=role,
        all_facilities=not bool(scope),all_cameras=True,
        **{right: right in ROLE_RIGHTS[role] for right in ALL_RIGHTS},
    )
    grant.full_clean()
    grant.save()
    if scope:
        grant.facilities.set([scope])
    return employee, grant


@login_required
@sensitive_post_parameters('staff-password1', 'staff-password2')
@require_http_methods(['GET','POST'])
def staff_dashboard(request):
    if not request.user.is_active or not request.user.is_superuser:
        raise PermissionDenied('Xodimlar huquqini faqat Platforma Super Admini boshqaradi.')
    operation=request.POST.get('action','') if request.method=='POST' else ''
    initial={}
    chosen_org=request.GET.get('organization','')
    if chosen_org.isdecimal() and Organization.objects.filter(pk=int(chosen_org),is_active=True).exists():
        initial['organization']=int(chosen_org)
    form=StaffSetupForm(
        request.POST if operation=='create' else None,
        prefix='staff',initial=initial,
    )
    operation_errors=[]
    if request.method=='POST':
        if operation=='create':
            if form.is_valid():
                try:
                    user, grant=create_employee(form.cleaned_data)
                except (ValidationError,IntegrityError,Organization.DoesNotExist,Facility.DoesNotExist) as exc:
                    if isinstance(exc, ValidationError):
                        for message in exc.messages:
                            form.add_error(None,message)
                    else:
                        form.add_error(None,'Xodimni yaratishda ma’lumotlar mos kelmadi.')
                else:
                    messages.success(request,'Xodim hisobi va tashkilot huquqi yaratildi. Login-parolni xodimga xavfsiz tarzda yetkazing.')
                    return redirect(reverse('staff_dashboard')+'?organization='+str(grant.organization_id)+'#staff-list')
        elif operation in ('revoke','activate'):
            membership_id=request.POST.get('membership_id','')
            if not membership_id.isdecimal():
                raise PermissionDenied('Noma’lum ruxsat.')
            with transaction.atomic():
                membership=get_object_or_404(
                    Membership.objects.select_for_update().select_related('user'),
                    pk=int(membership_id))
                if membership.user.is_superuser:
                    raise PermissionDenied('Super Admin huquqi bu ekrandan o‘zgartirilmaydi.')
                membership.is_active=(operation=='activate')
                membership.save(update_fields=['is_active'])
            messages.success(request,'Xodim ruxsatining holati yangilandi.')
            return redirect(reverse('staff_dashboard')+'#staff-list')
        else:
            raise PermissionDenied('Noma’lum amal.')

    rows=Membership.objects.select_related(
        'user','organization').prefetch_related('facilities').order_by('-id')
    if chosen_org.isdecimal():
        rows=rows.filter(organization_id=int(chosen_org))
    memberships=list(rows[:70])
    branches=list(Facility.objects.filter(is_active=True,organization__is_active=True)
        .order_by('organization__name','name')
        .values('id','organization_id'))
    return render(request,'warehouse/staff_dashboard.html',{
        'today':timezone.localdate(),
        'form':form,
        'memberships':memberships,
        'organizations':Organization.objects.all().order_by('name'),
        'organization_filter':chosen_org,
        'facility_mapping':{str(x['id']):x['organization_id'] for x in branches},
        'total_staff_grants':Membership.objects.count(),
        'operation_errors':operation_errors,
    })
