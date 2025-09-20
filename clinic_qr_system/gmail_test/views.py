from django.contrib import messages
from django.core.mail import send_mail
from django.shortcuts import render, redirect
from django.conf import settings
from clinic_qr_system.email_utils import send_test_email, get_email_provider_info

from .forms import GmailTestForm


def gmail_send_view(request):
    if request.method == 'POST':
        form = GmailTestForm(request.POST)
        if form.is_valid():
            recipient = form.cleaned_data['recipient']
            message = form.cleaned_data['message']
            try:
                # Get email provider info for display
                provider_info = get_email_provider_info()
                provider_name = provider_info.get('provider', 'unknown').upper()
                
                sent = send_test_email(
                    recipient_email=recipient,
                    message=message,
                    subject=f'{provider_name} Email Test'
                )
                
                if sent:
                    messages.success(request, f'Email sent to {recipient} via {provider_name}.')
                else:
                    messages.warning(request, f'Email not sent to {recipient}.')
                return redirect('gmail_test_send')
            except Exception as e:
                messages.error(request, f'Failed to send email: {e}')
    else:
        form = GmailTestForm()

    # Get email provider info for display
    provider_info = get_email_provider_info()
    return render(request, 'gmail_test/form.html', {
        'form': form,
        'provider_info': provider_info
    })
