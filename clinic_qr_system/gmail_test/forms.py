from django import forms


class GmailTestForm(forms.Form):
    recipient = forms.EmailField(label='Recipient Gmail', widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'recipient@gmail.com'}))
    message = forms.CharField(label='Message', widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 5, 'placeholder': 'Type your message here'}))


