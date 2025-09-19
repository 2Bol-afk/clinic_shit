"""
URL configuration for clinic_qr_system project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('django.contrib.auth.urls')),
    # Ensure password change URL works for patient flow
    path('accounts/password_change/', auth_views.PasswordChangeView.as_view(), name='password_change'),
    path('', RedirectView.as_view(url='/accounts/login/', permanent=False)),
    path('patients/', include('patients.urls')),
    path('visits/', include('visits.urls')),
    path('dashboard/', include('dashboard.urls')),
    path('gmail-test/', include('gmail_test.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
