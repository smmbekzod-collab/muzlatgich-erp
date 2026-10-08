"""Future warehouse views must call these server-side guards for every operation."""
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from .models import Camera, Membership, Organization

OPERATIONS = {'receive':'can_receive','dispatch':'can_dispatch','transfer':'can_transfer','payment':'can_take_payment','finance':'can_view_finance','tariff':'can_set_tariffs','debt_dispatch':'can_dispatch_on_debt','expense':'can_manage_expenses'}
def memberships(user):
    if not user.is_authenticated or not user.is_active:return Membership.objects.none()
    return Membership.objects.filter(user=user,is_active=True,organization__is_active=True)
def organizations(user):
    if user.is_authenticated and user.is_active and user.is_superuser:return Organization.objects.all()
    return Organization.objects.filter(pk__in=memberships(user).values('organization_id'))
def cameras(user):
    if user.is_authenticated and user.is_active and user.is_superuser:return Camera.objects.all()
    grants = memberships(user)
    return Camera.objects.filter(Q(organization_id__in=grants.filter(all_cameras=True).values('organization_id'))|Q(pk__in=grants.filter(all_cameras=False).values('cameras'))).filter(organization_id__in=grants.values('organization_id')).distinct()
def authorize(user,organization_id,camera_id,operation):
    if operation not in OPERATIONS:raise PermissionDenied('Noma’lum amal')
    if not user.is_authenticated or not user.is_active:raise PermissionDenied
    cam = cameras(user).filter(pk=camera_id,organization_id=organization_id,is_active=True,organization__is_active=True).first()
    if cam is None:raise PermissionDenied('Kamera uchun ruxsat yo‘q')
    if user.is_superuser:return cam
    grant = memberships(user).filter(organization_id=organization_id).first()
    if not grant or not getattr(grant,OPERATIONS[operation]):raise PermissionDenied('Amal uchun ruxsat yo‘q')
    if operation=='debt_dispatch' and not grant.can_dispatch:raise PermissionDenied
    return cam
