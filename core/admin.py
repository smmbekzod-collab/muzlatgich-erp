from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin
from django.contrib.admin.models import LogEntry
from django.core.exceptions import PermissionDenied
from django.db import transaction
from .models import Organization,Facility,Camera,Membership
from .forms import MembershipForm
from . import access

class AgroSite(admin.AdminSite):
    site_header = 'MUZLATGICH ERP · Boshqaruv'
    site_title = 'MUZLATGICH ERP'
    index_title = 'Boshqaruv paneli'
    index_template = 'admin/agro_index.html'
    def has_permission(self,request):
        u=request.user
        return u.is_active and u.is_staff and (u.is_superuser or access.memberships(u).exists())
    def index(self,request,extra_context=None):
        orgs = access.organizations(request.user)
        cams = access.cameras(request.user)
        cards = [{'organization':o,'count':cams.filter(organization=o).count()} for o in orgs]
        return super().index(request,{'cards':cards,'camera_count':cams.count(),'organization_count':orgs.count(),'is_platform_admin':request.user.is_superuser,**(extra_context or {})})
site=AgroSite(name='admin')

class ScopedAdmin(admin.ModelAdmin):
    actions = None
    def has_module_permission(self,request):return site.has_permission(request)
    def has_view_permission(self,request,obj=None):
        if not site.has_permission(request):return False
        return obj is None or self.get_queryset(request).filter(pk=obj.pk).exists()
    def has_add_permission(self,request):return request.user.is_active and request.user.is_superuser
    def has_change_permission(self,request,obj=None):return request.user.is_active and request.user.is_superuser
    def has_delete_permission(self,request,obj=None):return False
    def save_model(self,request,obj,form,change):
        if not request.user.is_superuser:raise PermissionDenied
        super().save_model(request,obj,form,change)
    def get_list_filter(self,request):return super().get_list_filter(request) if request.user.is_superuser else ()
    def changeform_view(self,request,object_id=None,form_url='',extra_context=None):
        # Serialize quota changes and camera creation on the same organization row.
        with transaction.atomic():
            if request.method=='POST' and request.user.is_superuser:
                org_id = request.POST.get('organization')
                if self.model is Organization:org_id=object_id
                if str(org_id).isdigit():Organization.objects.select_for_update().filter(pk=org_id).first()
            return super().changeform_view(request,object_id,form_url,extra_context)

@admin.register(Organization,site=site)
class OrganizationAdmin(ScopedAdmin):
    list_display = ['name','code','camera_limit','is_active']
    search_fields = ['name','code']
    def get_queryset(self,request):return access.organizations(request.user)

@admin.register(Facility,site=site)
class FacilityAdmin(ScopedAdmin):
    autocomplete_fields = ['organization']
    list_display = ['organization','name','region','district','code','is_active']
    list_filter = ['organization','region','is_active']
    search_fields = ['name','region','district','address','organization__name']
    def get_queryset(self,request):
        return Facility.objects.filter(organization__in=access.organizations(request.user)).select_related('organization')

@admin.register(Camera,site=site)
class CameraAdmin(ScopedAdmin):
    autocomplete_fields = ['organization','facility']
    list_display = ['organization','facility','number','name','capacity_kg','is_active']
    list_filter = ['organization','facility','is_active']
    search_fields = ['name','organization__name','facility__name']
    def get_queryset(self,request):return access.cameras(request.user).select_related('organization','facility')

@admin.register(Membership,site=site)
class MembershipAdmin(ScopedAdmin):
    form = MembershipForm
    list_display = ['user','organization','role','all_facilities','all_cameras','is_active']
    list_filter = ['organization','role','is_active']
    search_fields = ['user__username','organization__name']
    filter_horizontal = ['facilities','cameras']
    fieldsets = [('Kimga va qayerda',{'fields':('user','organization','role','is_active')}),('Kameralar',{'fields':('all_facilities','facilities','all_cameras','cameras')}),('Amallar',{'description':'Lavozimning o‘zi huquq bermaydi. Quyidagi huquqlar alohida tanlanadi. Kamera yaratish va huquq berish doimo super adminda.','fields':('can_receive','can_dispatch','can_transfer','can_take_payment','can_view_finance','can_set_tariffs','can_dispatch_on_debt','can_manage_expenses','can_monitor_environment')})]
    def get_queryset(self,request):
        if request.user.is_superuser:return Membership.objects.select_related('user','organization')
        return access.memberships(request.user)

@admin.register(get_user_model(),site=site)
class SuperUserAdmin(UserAdmin):
    def has_module_permission(self,request):return request.user.is_superuser
    def has_view_permission(self,request,obj=None):return request.user.is_superuser
    def has_add_permission(self,request):return request.user.is_superuser
    def has_change_permission(self,request,obj=None):return request.user.is_superuser
    def has_delete_permission(self,request,obj=None):return False
    def get_queryset(self,request):
        qs=super().get_queryset(request)
        return qs if request.user.is_superuser else qs.none()

@admin.register(LogEntry,site=site)
class AuditAdmin(admin.ModelAdmin):
    list_display=['action_time','user','content_type','object_repr','action_flag']
    list_filter=['action_flag','content_type']
    search_fields=['object_repr','user__username']
    def has_module_permission(self,request):return request.user.is_superuser
    def has_view_permission(self,request,obj=None):return request.user.is_superuser
    def has_add_permission(self,request):return False
    def has_change_permission(self,request,obj=None):return False
    def has_delete_permission(self,request,obj=None):return False
    def get_queryset(self,request):
        qs=super().get_queryset(request)
        return qs if request.user.is_superuser else qs.none()
