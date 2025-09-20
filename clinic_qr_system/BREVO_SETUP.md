# Brevo Email Integration Configuration

This document explains how to configure the Clinic QR System to use Brevo (formerly Sendinblue) for email sending.

## Required Environment Variables

Add these variables to your `.env` file:

```bash
# Brevo Email Configuration
# Get your API key from: https://app.brevo.com/settings/keys/api
BREVO_API_KEY=your_brevo_api_key_here

# SMTP Configuration (fallback if API key not provided)
BREVO_SMTP_HOST=smtp-relay.brevo.com
BREVO_SMTP_PORT=587
BREVO_SMTP_USER=your_brevo_smtp_user_here
BREVO_SMTP_PASSWORD=your_brevo_smtp_password_here

# Sender Configuration
BREVO_SENDER_EMAIL=noreply@yourdomain.com
BREVO_SENDER_NAME=Clinic QR System

# Email Provider Selection
# Options: 'brevo', 'gmail', 'console'
EMAIL_PROVIDER=brevo

# Test Email (for testing)
TEST_EMAIL_TO=test@example.com
```

## Setup Steps

1. **Create a Brevo Account**
   - Go to https://www.brevo.com/
   - Sign up for a free account
   - Verify your email address

2. **Get API Key**
   - Log into your Brevo dashboard
   - Go to Settings > API Keys
   - Create a new API key
   - Copy the key and add it to your `.env` file as `BREVO_API_KEY`

3. **Configure Sender Email**
   - In Brevo dashboard, go to Settings > Senders & IP
   - Add and verify your sender email address
   - Use this email in `BREVO_SENDER_EMAIL`

4. **SMTP Configuration (Optional)**
   - If you prefer SMTP over API, get your SMTP credentials from Brevo
   - Add them to `BREVO_SMTP_USER` and `BREVO_SMTP_PASSWORD`

## Features

### API Backend (Recommended)
- Uses Brevo's Transactional Email API
- Better reliability and delivery rates
- Supports attachments and HTML content
- Automatic retry and error handling

### SMTP Backend (Fallback)
- Uses standard SMTP protocol
- Fallback when API key is not available
- Compatible with existing Django email code

## Testing

### Test Email Command
```bash
python manage.py email_test --to your-email@example.com
```

### Test Email View
- Go to `/gmail_test/send/` in your browser
- Enter recipient email and message
- Click send to test Brevo integration

### Patient Registration Test
```bash
python manage.py add_patient_test
```

## Email Types Supported

1. **Patient Registration Emails**
   - Welcome message with patient code
   - QR code attachment
   - Login credentials (if applicable)

2. **Test Emails**
   - Simple test messages
   - Provider information display

3. **Notification Emails**
   - General notifications
   - HTML and plain text support

## Troubleshooting

### Common Issues

1. **API Key Not Working**
   - Verify the API key is correct
   - Check if the key has proper permissions
   - Ensure sender email is verified in Brevo

2. **SMTP Authentication Failed**
   - Verify SMTP credentials
   - Check if 2FA is enabled (may need app password)
   - Ensure SMTP user has proper permissions

3. **Emails Not Delivered**
   - Check spam folder
   - Verify sender email is not blacklisted
   - Check Brevo dashboard for delivery reports

### Debug Mode

Set `EMAIL_PROVIDER=console` in your `.env` file to see emails in the console instead of sending them.

## Migration from Gmail

To migrate from Gmail to Brevo:

1. Update `EMAIL_PROVIDER=brevo` in your `.env` file
2. Add Brevo configuration variables
3. Test with the email test command
4. Update any custom email templates if needed

The system will automatically use Brevo for all email sending once configured.
