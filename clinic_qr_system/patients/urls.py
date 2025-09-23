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
    # Removed old password change view to prevent account selection issues
    path('password/first/', views.password_first_change, name='patient_password_first'),
    path('qr-login/', views.qr_login, name='patient_qr_login'),
    path('api/qr-scan/', views.qr_scan_api, name='patient_qr_scan_api'),
    path('qr-download/', views.qr_code_download, name='patient_qr_download'),
    
    # Admin patient management
    path('admin/add/', views.admin_patient_add, name='admin_patient_add'),
    path('admin/edit/<int:pk>/', views.admin_patient_edit, name='admin_patient_edit'),
    path('admin/delete/<int:pk>/', views.admin_patient_delete, name='admin_patient_delete'),
    path('admin/list/', views.patient_list, name='admin_patient_list'),
    
    # Patient account management
    path('account/edit/', views.patient_account_edit, name='patient_account_edit'),
    path('account/password/', views.patient_password_change, name='patient_password_change'),
    path('account/delete/', views.patient_account_delete, name='patient_account_delete'),
]


