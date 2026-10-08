from django.urls import path
from . import views
urlpatterns=[path('',views.dashboard,name='dashboard'),path('receive/',views.intake,name='intake'),path('customers/',views.customers,name='customers'),path('tariffs/',views.tariffs,name='tariffs'),path('expenses/',views.expenses,name='expenses'),path('report/',views.report,name='report'),path('scan/',views.scanner,name='scanner'),path('lot/<uuid:pk>/',views.lot_detail,name='lot'),path('lot/<uuid:pk>/qr.png',views.qr_image,name='qr'),path('lot/<uuid:pk>/label/',views.label,name='label'),path('lot/<uuid:pk>/<str:kind>/',views.operation,name='operation'),path('receipt/<uuid:pk>/',views.receipt,name='receipt')]

urlpatterns.append(path("receipt/<uuid:pk>/reverse/",views.reverse_operation,name="reverse"))

urlpatterns.append(path("report/customers.csv",views.customer_csv,name="customer_csv"))
