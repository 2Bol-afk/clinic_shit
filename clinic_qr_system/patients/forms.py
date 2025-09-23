from django import forms
from .models import Patient
from django.contrib.auth.models import User


class PhotoValidationMixin:
    """Mixin to add photo validation to forms"""
    
    def clean_profile_photo(self):
        photo = self.cleaned_data.get('profile_photo')
        if photo:
            # Only validate if it's a new upload (not an existing ImageFieldFile)
            # ImageFieldFile objects don't have content_type attribute
            if hasattr(photo, 'content_type'):
                # Check file size (max 5MB)
                if photo.size > 5 * 1024 * 1024:
                    raise forms.ValidationError('Photo file size must be less than 5MB.')
                
                # Check file type
                allowed_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif']
                if photo.content_type not in allowed_types:
                    raise forms.ValidationError('Photo must be a JPEG, PNG, or GIF image.')
        
        return photo


class PatientRegistrationForm(PhotoValidationMixin, forms.ModelForm):
    class Meta:
        model = Patient
        fields = ['full_name', 'age', 'address', 'contact', 'email', 'profile_photo']
        widgets = {
            'full_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter your full name',
                'required': True
            }),
            'age': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter your age',
                'min': '0',
                'max': '150',
                'required': True
            }),
            'address': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'Enter your complete address',
                'rows': 3,
                'required': True
            }),
            'contact': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter your contact number',
                'required': True
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter your email address',
                'required': True
            }),
            'profile_photo': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*',
                'capture': 'environment',
                'required': True
            })
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set required fields
        for field_name in ['full_name', 'age', 'address', 'contact', 'email']:
            self.fields[field_name].required = True

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email:
            # Check if email already exists in Patient model
            if Patient.objects.filter(email__iexact=email).exists():
                raise forms.ValidationError('This email is already registered. Please use another one.')
            # Check if email already exists in User model
            if User.objects.filter(email__iexact=email).exists():
                raise forms.ValidationError('This email is already registered. Please use another one.')
        return email


class PatientSignupForm(PhotoValidationMixin, forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter at least 8 characters',
            'required': True,
            'minlength': '8'
        }),
        required=True,
        min_length=8,
        help_text='Password must be at least 8 characters long'
    )
    password_confirm = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Confirm your password',
            'required': True,
            'minlength': '8'
        }),
        required=True,
        min_length=8
    )

    class Meta:
        model = Patient
        fields = ['full_name', 'age', 'address', 'contact', 'email', 'profile_photo']
        widgets = {
            'full_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter your full name',
                'required': True
            }),
            'age': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter your age',
                'min': '0',
                'max': '150',
                'required': True
            }),
            'address': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'Enter your complete address',
                'rows': 3,
                'required': True
            }),
            'contact': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter your contact number',
                'required': True
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter your email address',
                'required': True
            }),
            'profile_photo': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*',
                'capture': 'environment',
                'required': True
            })
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set required fields
        for field_name in ['full_name', 'age', 'address', 'contact', 'email']:
            self.fields[field_name].required = True

    def clean_password(self):
        password = self.cleaned_data.get('password')
        if password and len(password) < 8:
            raise forms.ValidationError('Password must be at least 8 characters long.')
        return password

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email:
            # Check if email already exists in Patient model
            if Patient.objects.filter(email__iexact=email).exists():
                raise forms.ValidationError('This email is already registered. Please use another one.')
            # Check if email already exists in User model
            if User.objects.filter(email__iexact=email).exists():
                raise forms.ValidationError('This email is already registered. Please use another one.')
        return email

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get('password')
        password_confirm = cleaned.get('password_confirm')
        
        if password and password_confirm and password != password_confirm:
            self.add_error('password_confirm', 'Passwords do not match')
        
        return cleaned


DEPARTMENT_CHOICES = [
    ('Pediatrics', 'Pediatrics (Children’s Health)'),
    ('OB-GYN', 'Obstetrics and Gynecology (OB-GYN)'),
    ('Cardiology', 'Cardiology (Heart Care)'),
    ('Radiology', 'Radiology'),
    ('Surgery', 'Surgery'),
    ('Dermatology', 'Dermatology (Skin Care)'),
    ('ENT', 'ENT (Ear, Nose, Throat)'),
]

class DoctorForm(forms.Form):
    full_name = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter doctor\'s full name',
            'required': True
        }),
        required=True
    )
    specialization = forms.ChoiceField(
        choices=DEPARTMENT_CHOICES,
        label='Department',
        widget=forms.Select(attrs={
            'class': 'form-select',
            'placeholder': 'Select department/specialization',
            'required': True
        }),
        required=True
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter doctor\'s email address',
            'required': True
        }),
        required=True
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter new password (leave blank to keep current)'
        }),
        required=False,
        help_text='Set only to (re)set password'
    )

    def __init__(self, *args, **kwargs):
        self.instance = kwargs.pop('instance', None)
        super().__init__(*args, **kwargs)
        if self.instance:
            self.fields['full_name'].initial = self.instance.full_name
            self.fields['specialization'].initial = self.instance.specialization
            self.fields['email'].initial = self.instance.user.email

    def clean_email(self):
        email = self.cleaned_data['email']
        qs = User.objects.filter(email__iexact=email)
        if self.instance:
            qs = qs.exclude(pk=self.instance.user_id)
        if qs.exists():
            raise forms.ValidationError('Email is already in use')
        return email


class LoginForm(forms.Form):
    username = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your email or username',
            'required': True,
            'autofocus': True
        }),
        required=True,
        label='Email or Username'
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your password',
            'required': True
        }),
        required=True,
        label='Password'
    )


class AdminPatientForm(PhotoValidationMixin, forms.ModelForm):
    """Form for admin to add/edit patients"""
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter at least 8 characters',
            'required': False,
            'minlength': '8'
        }),
        required=False,
        min_length=8,
        help_text='Leave blank to keep current password. Must be at least 8 characters if provided.'
    )
    password_confirm = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Confirm password',
            'required': False,
            'minlength': '8'
        }),
        required=False,
        min_length=8
    )

    class Meta:
        model = Patient
        fields = ['full_name', 'age', 'address', 'contact', 'email', 'profile_photo']
        widgets = {
            'full_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter patient\'s full name',
                'required': True
            }),
            'age': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter patient\'s age',
                'min': '0',
                'max': '150',
                'required': True
            }),
            'address': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'Enter patient\'s complete address',
                'rows': 3,
                'required': True
            }),
            'contact': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter contact number',
                'required': True
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter email address',
                'required': True
            }),
            'profile_photo': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*',
                'capture': 'environment'
            })
        }

    def __init__(self, *args, **kwargs):
        self.instance = kwargs.pop('instance', None)
        super().__init__(*args, **kwargs)
        # Set required fields
        for field_name in ['full_name', 'age', 'address', 'contact', 'email']:
            self.fields[field_name].required = True

    def clean_password(self):
        password = self.cleaned_data.get('password')
        if password and len(password) < 8:
            raise forms.ValidationError('Password must be at least 8 characters long.')
        return password

    def clean_email(self):
        email = self.cleaned_data['email']
        qs = Patient.objects.filter(email__iexact=email)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('This email is already registered. Please use another one.')
        
        # Also check User model for email uniqueness
        user_qs = User.objects.filter(email__iexact=email)
        if self.instance and self.instance.user:
            user_qs = user_qs.exclude(pk=self.instance.user.pk)
        if user_qs.exists():
            raise forms.ValidationError('This email is already registered. Please use another one.')
        
        return email

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get('password')
        password_confirm = cleaned.get('password_confirm')
        
        if password and password != password_confirm:
            self.add_error('password_confirm', 'Passwords do not match')
        
        return cleaned


class PatientAccountForm(PhotoValidationMixin, forms.ModelForm):
    """Form for patients to edit their own account details"""
    class Meta:
        model = Patient
        fields = ['full_name', 'age', 'address', 'contact', 'email', 'profile_photo']
        widgets = {
            'full_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter your full name',
                'required': True
            }),
            'age': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter your age',
                'min': '0',
                'max': '150',
                'required': True
            }),
            'address': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'Enter your complete address',
                'rows': 3,
                'required': True
            }),
            'contact': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter your contact number',
                'required': True
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter your email address',
                'required': True
            }),
            'profile_photo': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*',
                'capture': 'environment'
            })
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set required fields
        for field_name in ['full_name', 'age', 'address', 'contact', 'email']:
            self.fields[field_name].required = True

    def clean_email(self):
        email = self.cleaned_data['email']
        qs = Patient.objects.filter(email__iexact=email)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('This email is already registered. Please use another one.')
        
        # Also check User model for email uniqueness
        user_qs = User.objects.filter(email__iexact=email)
        if self.instance and self.instance.user:
            user_qs = user_qs.exclude(pk=self.instance.user.pk)
        if user_qs.exists():
            raise forms.ValidationError('This email is already registered. Please use another one.')
        
        return email


class PatientPasswordChangeForm(forms.Form):
    """Form for patients to change their password"""
    current_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your current password',
            'required': True
        }),
        required=True,
        label='Current Password'
    )
    new_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter at least 8 characters',
            'required': True,
            'minlength': '8'
        }),
        required=True,
        min_length=8,
        label='New Password'
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Confirm new password',
            'required': True,
            'minlength': '8'
        }),
        required=True,
        min_length=8,
        label='Confirm New Password'
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_new_password(self):
        new_password = self.cleaned_data.get('new_password')
        if new_password and len(new_password) < 8:
            raise forms.ValidationError('New password must be at least 8 characters long.')
        return new_password

    def clean(self):
        cleaned = super().clean()
        current_password = cleaned.get('current_password')
        new_password = cleaned.get('new_password')
        confirm_password = cleaned.get('confirm_password')
        
        # Check current password
        if current_password and not self.user.check_password(current_password):
            self.add_error('current_password', 'Current password is incorrect')
        
        # Check new password confirmation
        if new_password and confirm_password and new_password != confirm_password:
            self.add_error('confirm_password', 'New passwords do not match')
        
        return cleaned


class DoctorPasswordChangeForm(forms.Form):
    """Form for doctors to change their password"""
    current_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your current password',
            'required': True
        }),
        required=True,
        label='Current Password'
    )
    new_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter at least 8 characters',
            'required': True,
            'minlength': '8'
        }),
        required=True,
        min_length=8,
        label='New Password'
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Confirm new password',
            'required': True,
            'minlength': '8'
        }),
        required=True,
        min_length=8,
        label='Confirm New Password'
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_new_password(self):
        new_password = self.cleaned_data.get('new_password')
        if new_password and len(new_password) < 8:
            raise forms.ValidationError('New password must be at least 8 characters long.')
        return new_password

    def clean(self):
        cleaned = super().clean()
        current_password = cleaned.get('current_password')
        new_password = cleaned.get('new_password')
        confirm_password = cleaned.get('confirm_password')
        
        # Check current password
        if current_password and not self.user.check_password(current_password):
            self.add_error('current_password', 'Current password is incorrect')
        
        # Check new password confirmation
        if new_password and confirm_password and new_password != confirm_password:
            self.add_error('confirm_password', 'New passwords do not match')
        
        return cleaned


class PatientDeleteForm(forms.Form):
    """Form for patients to confirm account deletion"""
    confirm_delete = forms.BooleanField(
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input',
            'required': True
        }),
        required=True,
        label='I understand that deleting my account will permanently remove all my data and cannot be undone'
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your password to confirm deletion',
            'required': True
        }),
        required=True,
        label='Password'
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_password(self):
        password = self.cleaned_data.get('password')
        if password and not self.user.check_password(password):
            raise forms.ValidationError('Password is incorrect')
        return password


