from django.urls import path
from . import views


urlpatterns = [
    path('', views.index, name='dashboard_index'),
    path('reception/', views.reception_dashboard, name='dashboard_reception'),
    path('doctor/', views.doctor_dashboard, name='dashboard_doctor'),
    path('lab/', views.lab_dashboard, name='dashboard_lab'),
    path('pharmacy/', views.pharmacy_dashboard, name='dashboard_pharmacy'),
    path('vaccination/', views.vaccination_dashboard, name='dashboard_vaccination'),
    path('post-login/', views.post_login_redirect, name='post_login_redirect'),
    # Doctor CRUD (admin only)
    path('doctors/', views.doctor_list, name='doctor_list'),
    path('doctors/new/', views.doctor_create, name='doctor_create'),
    path('doctors/<int:pk>/edit/', views.doctor_edit, name='doctor_edit'),
    path('doctors/<int:pk>/delete/', views.doctor_delete, name='doctor_delete'),
    # Doctor claim
    path('doctors/claim/', views.doctor_claim, name='doctor_claim'),
    # Reception edit/delete
    path('reception/<int:pk>/edit/', views.reception_edit, name='reception_edit'),
    path('reception/<int:pk>/delete/', views.reception_delete, name='reception_delete'),
]


