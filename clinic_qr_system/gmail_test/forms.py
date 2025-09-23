from django import forms


class GmailTestForm(forms.Form):
    recipient = forms.EmailField(
        label='Recipient Email',
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter recipient email address',
            'required': True
        }),
        required=True
    )
    message = forms.CharField(
        label='Message',
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 5,
            'placeholder': 'Type your message here',
            'required': True
        }),
        required=True
    )


