from django.urls import path
from . import views


urlpatterns = [
    path('', views.register, name='patient_register'),
    path('success/', views.register_success, name='patient_register_success'),
    path('list/', views.patient_list, name='patient_list'),
    path('<int:pk>/', views.patient_detail, name='patient_detail'),
    path('reports/daily.csv', views.report_daily_csv, name='report_daily_csv'),
    path('reports/daily.xlsx', views.report_daily_xlsx, name='report_daily_xlsx'),
    path('portal/', views.portal_home, name='patient_portal'),
    path('signup/', views.signup, name='patient_signup'),
]


