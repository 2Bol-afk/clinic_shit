from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import Patient, StaffProfile, Doctor


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ['full_name', 'patient_code', 'email', 'age', 'contact', 'created_at', 'profile_photo_display']
    list_filter = ['created_at', 'age']
    search_fields = ['full_name', 'email', 'patient_code', 'contact']
    readonly_fields = ['patient_code', 'created_at', 'qr_code_display', 'profile_photo_display']
    fieldsets = (
        ('Basic Information', {
            'fields': ('user', 'full_name', 'email', 'patient_code', 'age', 'contact', 'address')
        }),
        ('Profile', {
            'fields': ('profile_photo', 'profile_photo_display', 'qr_code_display')
        }),
        ('Security', {
            'fields': ('must_change_password',)
        }),
        ('Timestamps', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    
    def profile_photo_display(self, obj):
        if obj.profile_photo:
            return format_html('<img src="{}" width="50" height="50" style="border-radius: 50%;" />', obj.profile_photo.url)
        return "No Photo"
    profile_photo_display.short_description = "Profile Photo"
    
    def qr_code_display(self, obj):
        if obj.qr_code:
            return format_html('<img src="{}" width="100" height="100" />', obj.qr_code.url)
        return "No QR Code"
    qr_code_display.short_description = "QR Code"
    
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # If email changed, regenerate QR code
        if change and 'email' in form.changed_data:
            from .utils import generate_qr_code
            generate_qr_code(obj)


@admin.register(StaffProfile)
class StaffProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'role', 'full_name', 'email', 'is_active']
    list_filter = ['role', 'user__is_active', 'user__date_joined']
    search_fields = ['user__username', 'user__first_name', 'user__last_name', 'user__email']
    readonly_fields = ['user_link']
    
    def full_name(self, obj):
        return f"{obj.user.first_name} {obj.user.last_name}".strip() or obj.user.username
    full_name.short_description = "Full Name"
    
    def email(self, obj):
        return obj.user.email
    email.short_description = "Email"
    
    def is_active(self, obj):
        return obj.user.is_active
    is_active.short_description = "Active"
    is_active.boolean = True
    
    def user_link(self, obj):
        url = reverse('admin:auth_user_change', args=[obj.user.id])
        return format_html('<a href="{}">{}</a>', url, obj.user.username)
    user_link.short_description = "User Account"


@admin.register(Doctor)
class DoctorAdmin(admin.ModelAdmin):
    list_display = ['full_name', 'specialization', 'user', 'email', 'is_active', 'must_change_password']
    list_filter = ['specialization', 'must_change_password', 'user__is_active']
    search_fields = ['full_name', 'user__username', 'user__email']
    readonly_fields = ['user_link']
    
    def email(self, obj):
        return obj.user.email
    email.short_description = "Email"
    
    def is_active(self, obj):
        return obj.user.is_active
    is_active.short_description = "Active"
    is_active.boolean = True
    
    def user_link(self, obj):
        url = reverse('admin:auth_user_change', args=[obj.user.id])
        return format_html('<a href="{}">{}</a>', url, obj.user.username)
    user_link.short_description = "User Account"


# Customize User Admin
class StaffProfileInline(admin.StackedInline):
    model = StaffProfile
    can_delete = False
    verbose_name_plural = 'Staff Profile'


class UserAdmin(BaseUserAdmin):
    inlines = (StaffProfileInline,)
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'is_active', 'date_joined', 'get_role')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'date_joined', 'staff_profile__role')
    search_fields = ('username', 'first_name', 'last_name', 'email')
    
    def get_role(self, obj):
        try:
            return obj.staff_profile.get_role_display()
        except:
            return "Patient"
    get_role.short_description = "Role"


# Unregister the default User admin and register our custom one
admin.site.unregister(User)
admin.site.register(User, UserAdmin)
