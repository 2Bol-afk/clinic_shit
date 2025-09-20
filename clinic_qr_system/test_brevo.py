#!/usr/bin/env python
"""
Test script for Brevo email integration.
Run this script to test the Brevo email configuration.
"""
import os
import sys
import django

# Add the project directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'clinic_qr_system.settings')
django.setup()

from clinic_qr_system.email_utils import send_test_email, get_email_provider_info
from django.conf import settings


def test_brevo_configuration():
    """Test Brevo email configuration and send a test email."""
    print("=== Brevo Email Integration Test ===\n")
    
    # Get email provider info
    provider_info = get_email_provider_info()
    
    print("Email Configuration:")
    print(f"  Provider: {provider_info.get('provider', 'unknown').upper()}")
    print(f"  Backend: {provider_info.get('backend', 'unknown')}")
    print(f"  From Email: {provider_info.get('from_email', 'unknown')}")
    
    if provider_info.get('provider') == 'brevo':
        print(f"  Sender Name: {provider_info.get('sender_name', 'unknown')}")
        print(f"  Sender Email: {provider_info.get('sender_email', 'unknown')}")
        print(f"  API Key Configured: {provider_info.get('api_key_configured', False)}")
        print(f"  SMTP Host: {provider_info.get('smtp_host', 'unknown')}")
        print(f"  SMTP Port: {provider_info.get('smtp_port', 'unknown')}")
    
    print("\n" + "="*50)
    
    # Test email sending
    test_email = input("Enter test email address (or press Enter to skip): ").strip()
    
    if not test_email:
        print("Skipping email test.")
        return
    
    try:
        print(f"\nSending test email to {test_email}...")
        
        sent = send_test_email(
            recipient_email=test_email,
            message="This is a test email from Clinic QR System using Brevo integration.",
            subject="Brevo Integration Test"
        )
        
        if sent:
            print("✅ Test email sent successfully!")
        else:
            print("❌ Test email failed to send.")
            
    except Exception as e:
        print(f"❌ Error sending test email: {e}")


def check_environment_variables():
    """Check if required environment variables are set."""
    print("=== Environment Variables Check ===\n")
    
    required_vars = [
        'BREVO_API_KEY',
        'BREVO_SENDER_EMAIL',
        'EMAIL_PROVIDER'
    ]
    
    optional_vars = [
        'BREVO_SMTP_USER',
        'BREVO_SMTP_PASSWORD',
        'BREVO_SENDER_NAME'
    ]
    
    print("Required Variables:")
    for var in required_vars:
        value = os.getenv(var)
        if value:
            # Mask sensitive values
            if 'KEY' in var or 'PASSWORD' in var:
                masked_value = value[:4] + '*' * (len(value) - 8) + value[-4:] if len(value) > 8 else '***'
                print(f"  ✅ {var}: {masked_value}")
            else:
                print(f"  ✅ {var}: {value}")
        else:
            print(f"  ❌ {var}: Not set")
    
    print("\nOptional Variables:")
    for var in optional_vars:
        value = os.getenv(var)
        if value:
            if 'PASSWORD' in var:
                masked_value = value[:4] + '*' * (len(value) - 8) + value[-4:] if len(value) > 8 else '***'
                print(f"  ✅ {var}: {masked_value}")
            else:
                print(f"  ✅ {var}: {value}")
        else:
            print(f"  ⚠️  {var}: Not set (using default)")


if __name__ == "__main__":
    check_environment_variables()
    print("\n")
    test_brevo_configuration()
