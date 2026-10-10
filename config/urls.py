from django.urls import path,include
from django.http import JsonResponse
from django.shortcuts import redirect
from core.admin import site
from core.bootstrap import setup_superadmin
from warehouse.views import manifest,service_worker
urlpatterns = [path('',lambda request:redirect('/app/')),path('health/',lambda request:JsonResponse({'status':'ok'})),path('setup/',setup_superadmin,name='setup_superadmin'),path('admin/',site.urls),path('app/',include('warehouse.urls')),path('manifest.json',manifest),path('sw.js',service_worker)]
