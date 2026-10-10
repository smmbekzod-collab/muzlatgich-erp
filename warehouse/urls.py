from django.urls import path
from . import views
from core import onboarding, staff_onboarding
from . import environment_views,telegram_admin
urlpatterns=[path('',views.dashboard,name='dashboard'),path('platform/',onboarding.platform_dashboard,name='platform_dashboard'),path('platform/staff/',staff_onboarding.staff_dashboard,name='staff_dashboard'),path('receive/',views.intake,name='intake'),path('customers/',views.customers,name='customers'),path('tariffs/',views.tariffs,name='tariffs'),path('expenses/',views.expenses,name='expenses'),path('report/',views.report,name='report'),path('scan/',views.scanner,name='scanner'),path('lot/<uuid:pk>/',views.lot_detail,name='lot'),path('lot/<uuid:pk>/qr.png',views.qr_image,name='qr'),path('lot/<uuid:pk>/label/',views.label,name='label'),path('lot/<uuid:pk>/<str:kind>/',views.operation,name='operation'),path('receipt/<uuid:pk>/',views.receipt,name='receipt')]

urlpatterns.append(path("receipt/<uuid:pk>/reverse/",views.reverse_operation,name="reverse"))

urlpatterns.append(path("report/customers.csv",views.customer_csv,name="customer_csv"))

urlpatterns.append(path("report/customer.xlsx",views.customer_excel,name="customer_excel"))
urlpatterns.append(path('monitor/',environment_views.monitor_overview,name='monitor_overview'))
urlpatterns.append(path('monitor/director/',environment_views.director_monitor,name='director_monitor'))
urlpatterns.append(path('platform/telegram/',telegram_admin.telegram_destinations,name='telegram_destinations'))
urlpatterns.append(path('monitor/camera/<int:camera_id>/',environment_views.monitor_camera,name='monitor_camera'))
urlpatterns.append(path('monitor/camera/<int:camera_id>/export.csv',environment_views.monitor_csv,name='monitor_csv'))
urlpatterns.append(path("rentals/",views.rentals,name="rentals"))
urlpatterns.append(path("rentals/invoice/<int:pk>/",views.rental_invoice,name="rental_invoice"))
