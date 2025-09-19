from django.contrib import messages
from django.core.mail import send_mail
from django.shortcuts import render, redirect
from django.conf import settings

from .forms import GmailTestForm


def gmail_send_view(request):
    if request.method == 'POST':
        form = GmailTestForm(request.POST)
        if form.is_valid():
            recipient = form.cleaned_data['recipient']
            message = form.cleaned_data['message']
            try:
                send_mail(
                    subject='Gmail SMTP Test',
                    message=message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[recipient],
                    fail_silently=False,
                )
                messages.success(request, f'Email sent to {recipient}.')
                return redirect('gmail_test_send')
            except Exception as e:
                messages.error(request, f'Failed to send email: {e}')
    else:
        form = GmailTestForm()

    return render(request, 'gmail_test/form.html', {'form': form})

from django.shortcuts import render

# Create your views here.
