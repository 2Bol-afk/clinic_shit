from django.urls import path
from . import views

app_name = 'vaccinations'

urlpatterns = [
    # Dashboard
    path('', views.vaccination_dashboard, name='dashboard'),
    
    # Vaccine Types
    path('vaccine-types/', views.vaccine_type_list, name='vaccine_type_list'),
    path('vaccine-types/create/', views.vaccine_type_create, name='vaccine_type_create'),
    path('vaccine-types/<int:pk>/edit/', views.vaccine_type_edit, name='vaccine_type_edit'),
    
    # Patient Vaccinations
    path('vaccinations/', views.patient_vaccination_list, name='patient_vaccination_list'),
    path('vaccinations/<int:pk>/', views.patient_vaccination_detail, name='patient_vaccination_detail'),
    path('vaccinations/schedule/', views.vaccination_schedule, name='vaccination_schedule'),
    path('vaccinations/timeline/<int:patient_id>/', views.patient_vaccination_timeline, name='patient_vaccination_timeline'),
    
    # Dynamic Vaccination Form
    path('vaccinate/', views.dynamic_vaccination_form, name='dynamic_vaccination_form'),
    
    # Vaccine Doses
    path('doses/<int:pk>/administer/', views.administer_dose, name='administer_dose'),
    
    # Reminders and Bulk Operations
    path('reminders/send/', views.send_reminders, name='send_reminders'),
    path('bulk/', views.bulk_vaccination, name='bulk_vaccination'),
    
    # AJAX endpoints
    path('ajax/vaccine-info/', views.get_vaccine_info, name='get_vaccine_info'),
    path('ajax/vaccine-schedule/', views.get_vaccine_schedule, name='get_vaccine_schedule'),
    path('ajax/search-patients/', views.search_patients, name='search_patients'),
]
