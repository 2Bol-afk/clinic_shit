from django import forms
from django.forms import inlineformset_factory
from .models import Prescription, PrescriptionMedicine, Visit, LabResult, VaccinationRecord


class PrescriptionMedicineForm(forms.ModelForm):
    """Form for individual medicine items in a prescription"""
    
    class Meta:
        model = PrescriptionMedicine
        fields = ['drug_name', 'dosage', 'frequency', 'duration', 'quantity', 'special_instructions']
        widgets = {
            'drug_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Amoxicillin, Paracetamol'
            }),
            'dosage': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., 500mg, 10ml'
            }),
            'frequency': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., 3 times daily, every 8 hours'
            }),
            'duration': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., 7 days, 2 weeks'
            }),
            'quantity': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., 30 tablets, 1 bottle'
            }),
            'special_instructions': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Special instructions for this medicine'
            })
        }


class PrescriptionForm(forms.ModelForm):
    """Form for creating/editing prescriptions"""
    
    class Meta:
        model = Prescription
        fields = ['pharmacy_notes']
        widgets = {
            'pharmacy_notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Notes from pharmacy staff (substitutions, etc.)'
            })
        }


class PrescriptionDispenseForm(forms.ModelForm):
    """Form for dispensing prescriptions"""
    
    class Meta:
        model = Prescription
        fields = ['pharmacy_notes']
        widgets = {
            'pharmacy_notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Notes about dispensing (substitutions, etc.)'
            })
        }


class PrescriptionMedicineDispenseForm(forms.ModelForm):
    """Form for dispensing individual medicines"""
    
    class Meta:
        model = PrescriptionMedicine
        fields = ['dispensed_quantity', 'substitution_notes']
        widgets = {
            'dispensed_quantity': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Actual quantity dispensed'
            }),
            'substitution_notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Notes if medicine was substituted'
            })
        }


# Inline formset for prescription medicines
PrescriptionMedicineFormSet = inlineformset_factory(
    Prescription,
    PrescriptionMedicine,
    form=PrescriptionMedicineForm,
    extra=1,
    can_delete=True,
    fields=['drug_name', 'dosage', 'frequency', 'duration', 'quantity', 'special_instructions']
)


class PrescriptionSearchForm(forms.Form):
    """Form for searching prescriptions"""
    search = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Search by patient name, doctor name, or medicine'
        })
    )
    
    status = forms.ChoiceField(
        choices=[('', 'All Status')] + Prescription.Status.choices,
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )
    
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )


class LabResultForm(forms.ModelForm):
    """Form for lab results"""
    
    class Meta:
        model = LabResult
        fields = ['lab_type', 'status', 'results']
        widgets = {
            'lab_type': forms.Select(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'results': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Enter lab results here...'
            })
        }


class VaccinationForm(forms.ModelForm):
    """Form for vaccination records"""
    
    class Meta:
        model = VaccinationRecord
        fields = ['vaccine_type', 'status', 'details']
        widgets = {
            'vaccine_type': forms.Select(attrs={
                'class': 'form-control',
                'id': 'vaccine_type_select'
            }),
            'status': forms.Select(attrs={
                'class': 'form-control'
            }),
            'details': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Additional vaccination details...'
            })
        }