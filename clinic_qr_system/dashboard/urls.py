from django.urls import path
from . import views


urlpatterns = [
    path('', views.index, name='dashboard_index'),
    path('reception/', views.reception_dashboard, name='dashboard_reception'),
    path('doctor/', views.doctor_dashboard, name='dashboard_doctor'),
    path('lab/', views.lab_dashboard, name='dashboard_lab'),
    path('lab/results/demo/', views.lab_results_demo, name='lab_results_demo'),
    path('lab/work/<int:pk>/', views.lab_work, name='lab_work'),
    path('lab/claim/', views.lab_claim, name='lab_claim'),
    path('lab/receive/', views.lab_receive, name='lab_receive'),
    path('lab/<int:pk>/done/', views.lab_mark_done, name='lab_mark_done'),
    path('pharmacy/', views.pharmacy_dashboard, name='dashboard_pharmacy'),
    path('vaccination/', views.vaccination_dashboard, name='dashboard_vaccination'),
    # Lightweight API for pharmacy/doctor UI
    path('api/patient_by_code/<str:code>/', views.api_patient_by_code, name='api_patient_by_code'),
    path('reports/', views.reports, name='dashboard_reports'),
    path('post-login/', views.post_login_redirect, name='post_login_redirect'),
    # Doctor CRUD (admin only)
    path('doctors/', views.doctor_list, name='doctor_list'),
    path('doctors/new/', views.doctor_create, name='doctor_create'),
    path('doctors/<int:pk>/edit/', views.doctor_edit, name='doctor_edit'),
    path('doctors/<int:pk>/delete/', views.doctor_delete, name='doctor_delete'),
    # Doctor claim
    path('doctors/claim/', views.doctor_claim, name='doctor_claim'),
    path('doctors/verify/', views.doctor_verify_arrival, name='doctor_verify_arrival'),
    path('doctors/consult/<int:rid>/', views.doctor_consult, name='doctor_consult'),
    path('doctors/consult/<int:rid>/finish/', views.doctor_finish_inprogress, name='doctor_finish_inprogress'),
    path('doctors/consult/edit/<int:did>/', views.doctor_consult_edit, name='doctor_consult_edit'),
    # Reception edit/delete
    path('reception/<int:pk>/edit/', views.reception_edit, name='reception_edit'),
    path('reception/<int:pk>/delete/', views.reception_delete, name='reception_delete'),
]


