from django import forms
from .models import LabResult, Laboratory, VaccinationType


LAB_FIELDS = {
    Laboratory.HEMATOLOGY: [
        ('hemoglobin', 'Hemoglobin'),
        ('hematocrit', 'Hematocrit'),
        ('wbc', 'WBC Count'),
        ('rbc', 'RBC Count'),
        ('platelet', 'Platelet Count'),
        ('remarks', 'Remarks'),
    ],
    Laboratory.CLINICAL_MICROSCOPY: [
        ('color', 'Color'),
        ('appearance', 'Appearance'),
        ('sg', 'Specific Gravity'),
        ('ph', 'pH'),
        ('protein', 'Protein'),
        ('glucose', 'Glucose'),
        ('blood', 'Blood'),
        ('microscopy', 'Microscopy Findings'),
    ],
    Laboratory.CLINICAL_CHEMISTRY: [
        ('glucose', 'Glucose'),
        ('cholesterol', 'Cholesterol'),
        ('triglycerides', 'Triglycerides'),
        ('ldl', 'LDL'),
        ('hdl', 'HDL'),
        ('creatinine', 'Creatinine'),
        ('uric_acid', 'Uric Acid'),
        ('remarks', 'Remarks'),
    ],
    Laboratory.IMMUNOLOGY: [
        ('test_type', 'Test Type'),
        ('result', 'Result'),
        ('level', 'Antibody/Antigen Level'),
        ('remarks', 'Remarks'),
    ],
    Laboratory.MICROBIOLOGY: [
        ('specimen', 'Specimen Type'),
        ('organism', 'Organism Isolated'),
        ('gram_stain', 'Gram Stain Result'),
        ('sensitivity', 'Antibiotic Sensitivity'),
        ('remarks', 'Remarks'),
    ],
    Laboratory.PATHOLOGY: [
        ('specimen', 'Specimen Type'),
        ('gross', 'Gross Description'),
        ('microscopic', 'Microscopic Findings'),
        ('diagnosis', 'Diagnosis/Interpretation'),
        ('remarks', 'Remarks'),
    ],
}


class LabResultForm(forms.Form):
    lab_type = forms.ChoiceField(choices=Laboratory.choices, required=True, label='Laboratory Test Type')

    def __init__(self, *args, **kwargs):
        self.instance: LabResult | None = kwargs.pop('instance', None)
        initial = kwargs.get('initial') or {}
        lab_type_value = initial.get('lab_type') or (self.instance.lab_type if self.instance else None)
        super().__init__(*args, **kwargs)
        # Pre-select lab_type in form
        if lab_type_value:
            self.fields['lab_type'].initial = lab_type_value
        # Ensure select styling
        self.fields['lab_type'].widget.attrs['class'] = (
            (self.fields['lab_type'].widget.attrs.get('class', '') + ' form-select').strip()
        )
        # Build dynamic fields
        lt = lab_type_value or Laboratory.HEMATOLOGY
        for name, label in LAB_FIELDS.get(lt, []):
            self.fields[name] = forms.CharField(label=label, required=False)
            # Apply consistent control styling
            self.fields[name].widget.attrs['class'] = (
                (self.fields[name].widget.attrs.get('class', '') + ' form-control').strip()
            )
            # Prefill from instance JSON
            if self.instance and isinstance(self.instance.results, dict):
                self.fields[name].initial = self.instance.results.get(name, '')

    def to_results_json(self) -> dict:
        data = {}
        for name, field in self.fields.items():
            if name == 'lab_type':
                continue
            val = self.cleaned_data.get(name)
            if val:
                data[name] = val
        return data



VACC_FIELDS: dict[str, list[tuple[str, str]]] = {
    VaccinationType.COVID19: [
        ('brand', 'Vaccine Brand'),
        ('dose_number', 'Dose Number'),
        ('batch', 'Batch/Lot Number'),
        ('expiry', 'Expiry Date'),
        ('site', 'Site of Injection'),
        ('date_admin', 'Date of Administration'),
        ('admin_by', 'Administered By'),
        ('remarks', 'Remarks'),
    ],
    VaccinationType.INFLUENZA: [
        ('brand', 'Vaccine Brand'),
        ('strain', 'Yearly Strain/Type'),
        ('batch', 'Batch/Lot Number'),
        ('expiry', 'Expiry Date'),
        ('site', 'Site of Injection'),
        ('date_admin', 'Date of Administration'),
        ('admin_by', 'Administered By'),
        ('remarks', 'Remarks'),
    ],
    VaccinationType.HEPATITIS_B: [
        ('dose_number', 'Dose Number'),
        ('batch', 'Batch/Lot Number'),
        ('expiry', 'Expiry Date'),
        ('site', 'Site of Injection'),
        ('date_admin', 'Date of Administration'),
        ('admin_by', 'Administered By'),
        ('remarks', 'Remarks'),
    ],
    VaccinationType.TETANUS: [
        ('vaccine_type', 'Vaccine Type'),
        ('dose_number', 'Dose Number'),
        ('batch', 'Batch/Lot Number'),
        ('expiry', 'Expiry Date'),
        ('site', 'Site of Injection'),
        ('date_admin', 'Date of Administration'),
        ('admin_by', 'Administered By'),
        ('remarks', 'Remarks'),
    ],
    VaccinationType.MMR: [
        ('dose_number', 'Dose Number'),
        ('batch', 'Batch/Lot Number'),
        ('expiry', 'Expiry Date'),
        ('site', 'Site of Injection'),
        ('date_admin', 'Date of Administration'),
        ('admin_by', 'Administered By'),
        ('remarks', 'Remarks'),
    ],
    VaccinationType.POLIO: [
        ('vaccine_type', 'Vaccine Type (OPV/IPV)'),
        ('dose_number', 'Dose Number'),
        ('batch', 'Batch/Lot Number'),
        ('expiry', 'Expiry Date'),
        ('site', 'Site of Injection (if injectable)'),
        ('date_admin', 'Date of Administration'),
        ('admin_by', 'Administered By'),
        ('remarks', 'Remarks'),
    ],
    VaccinationType.VARICELLA: [
        ('dose_number', 'Dose Number'),
        ('batch', 'Batch/Lot Number'),
        ('expiry', 'Expiry Date'),
        ('site', 'Site of Injection'),
        ('date_admin', 'Date of Administration'),
        ('admin_by', 'Administered By'),
        ('remarks', 'Remarks'),
    ],
    VaccinationType.HPV: [
        ('brand', 'Vaccine Brand'),
        ('dose_number', 'Dose Number'),
        ('batch', 'Batch/Lot Number'),
        ('expiry', 'Expiry Date'),
        ('site', 'Site of Injection'),
        ('date_admin', 'Date of Administration'),
        ('admin_by', 'Administered By'),
        ('remarks', 'Remarks'),
    ],
}


class VaccinationForm(forms.Form):
    vaccine_type = forms.ChoiceField(choices=VaccinationType.choices, required=True, label='Vaccine Type')

    def __init__(self, *args, **kwargs):
        self.instance = kwargs.pop('instance', None)
        initial = kwargs.get('initial') or {}
        vt_value = initial.get('vaccine_type') or (getattr(self.instance, 'vaccine_type', None))
        super().__init__(*args, **kwargs)
        if vt_value:
            self.fields['vaccine_type'].initial = vt_value
        vt = vt_value or VaccinationType.COVID19
        for name, label in VACC_FIELDS.get(vt, []):
            self.fields[name] = forms.CharField(label=label, required=False)
            if self.instance and isinstance(getattr(self.instance, 'details', {}), dict):
                self.fields[name].initial = getattr(self.instance, 'details', {}).get(name, '')

    def to_details_json(self) -> dict:
        data = {}
        for name, field in self.fields.items():
            if name == 'vaccine_type':
                continue
            val = self.cleaned_data.get(name)
            if val:
                data[name] = val
        return data

