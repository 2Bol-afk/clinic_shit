from django.urls import path
from . import views


urlpatterns = [
    path('send/', views.gmail_send_view, name='gmail_test_send'),
]


