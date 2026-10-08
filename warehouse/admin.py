from django.contrib import admin
from core.admin import site
from .models import Customer,Tariff,Lot,Operation,Expense
from core.access import organizations,cameras

class ReadOnlyAdmin(admin.ModelAdmin):
    actions=None
    def has_module_permission(self,request):return request.user.is_superuser
    def has_view_permission(self,request,obj=None):return request.user.is_superuser
    def has_add_permission(self,request):return False
    def has_change_permission(self,request,obj=None):return False
    def has_delete_permission(self,request,obj=None):return False
    def get_queryset(self,request):
        qs=super().get_queryset(request)
        return qs if request.user.is_superuser else qs.none()

@admin.register(Lot,site=site)
class LotAdmin(ReadOnlyAdmin):
    list_display=['id','organization','camera','customer','product','boxes','gross','closed_on']
    list_filter=['organization','service','closed_on']
    search_fields=['product','customer__name']
@admin.register(Operation,site=site)
class OperationAdmin(ReadOnlyAdmin):
    list_display=['id','lot','kind','date','boxes','charge','payment','created_by']
    list_filter=['kind','date','camera__organization']
for model in [Customer,Tariff,Expense]:site.register(model,ReadOnlyAdmin)
