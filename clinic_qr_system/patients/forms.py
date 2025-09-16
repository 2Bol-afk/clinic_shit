from django import forms
from .models import Patient
from django.contrib.auth.models import User


class PatientRegistrationForm(forms.ModelForm):
    class Meta:
        model = Patient
        fields = ['full_name', 'age', 'address', 'contact', 'email']


class PatientSignupForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput)
    password_confirm = forms.CharField(widget=forms.PasswordInput)

    class Meta:
        model = Patient
        fields = ['full_name', 'age', 'address', 'contact', 'email']

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('password') != cleaned.get('password_confirm'):
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
    full_name = forms.CharField(max_length=255)
    specialization = forms.ChoiceField(choices=DEPARTMENT_CHOICES, label='Department')
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput, required=False, help_text='Set only to (re)set password')

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


