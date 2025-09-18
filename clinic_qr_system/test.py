from django.test import TestCase, override_settings
from django.core import mail
from django.urls import reverse
from django.conf import settings
from patients.models import Patient
from django.contrib.auth.models import User, Group


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class RegistrationEmailTests(TestCase):
    """
    End-to-end tests for registration flows that must generate a QR image and
    email it to the patient. Uses locmem backend so no real emails are sent.
    Compatible with Django 5.1.1.
    """

    def setUp(self):
        # Ensure Patient group exists
        Group.objects.get_or_create(name='Patient')

    def _assert_qr_attachment(self, email_obj):
        # There should be at least one PNG attachment
        self.assertTrue(email_obj.attachments, 'Email has no attachments')
        png_att = None
        for att in email_obj.attachments:
            # attachment can be (filename, content, mimetype)
            if isinstance(att, tuple) and len(att) == 3 and att[2] == 'image/png':
                png_att = att
                break
        self.assertIsNotNone(png_att, 'Email does not contain a PNG QR attachment')
        self.assertTrue(png_att[0].startswith('qr_'), 'QR filename should start with qr_')
        self.assertGreater(len(png_att[1]), 0, 'QR attachment content is empty')

    def test_normal_registration_sends_qr(self):
        """Simulate patient registration via normal form and verify QR email."""
        payload = {
            'full_name': 'Alice Test',
            'age': 28,
            'address': '123 Test St',
            'contact': '0917-000-0000',
            'email': 'alice@example.com',
        }
        # Post to registration endpoint
        resp = self.client.post(reverse('patient_register'), data=payload, follow=True)
        self.assertEqual(resp.status_code, 200)

        # Patient created
        p = Patient.objects.filter(email='alice@example.com').first()
        self.assertIsNotNone(p, 'Patient was not created')
        self.assertTrue(p.patient_code, 'Patient code not generated')
        # QR saved on model
        self.assertTrue(bool(p.qr_code), 'QR image not saved on patient')

        # Email(s) sent with QR attached (some flows send 2 messages)
        self.assertGreaterEqual(len(mail.outbox), 1, 'Expected at least 1 email to be sent')
        # Find an email that mentions the patient code and has a PNG attachment
        matched = None
        for m in mail.outbox:
            body_ok = p.patient_code in (m.body or '')
            has_png = any(isinstance(att, tuple) and len(att) == 3 and att[2] == 'image/png' for att in (m.attachments or []))
            if body_ok and has_png:
                matched = m
                break
        self.assertIsNotNone(matched, 'No email found with patient code and QR attachment')
        self.assertIn('Your', matched.subject)
        self._assert_qr_attachment(matched)

    def test_walkin_registration_sends_qr(self):
        """Simulate receptionist walk-in; verify QR email with temp password content."""
        # Log in a reception user to access walk-in view if required
        u = User.objects.create_user('recept1', password='pass1234')
        u.groups.add(Group.objects.get_or_create(name='Reception')[0])
        self.client.login(username='recept1', password='pass1234')

        payload = {
            'full_name': 'Bob Walkin',
            'age': 34,
            'address': '456 Walk St',
            'contact': '0917-111-1111',
            'email': 'bob@example.com',
            'reception_visit_type': 'laboratory',
            'department': '',
        }
        resp = self.client.post(reverse('reception_walkin'), data=payload, follow=True)
        self.assertEqual(resp.status_code, 200)

        p = Patient.objects.filter(email='bob@example.com').first()
        self.assertIsNotNone(p, 'Walk-in patient not created')
        self.assertTrue(bool(p.qr_code), 'Walk-in QR image not saved')

        # Email sent with QR and temp password mention
        self.assertGreaterEqual(len(mail.outbox), 1)
        email_obj = mail.outbox[-1]
        self.assertIn('Your Patient QR Code', email_obj.subject)
        self.assertIn(p.patient_code, email_obj.body)
        # temp password note may be present when account created here
        self.assertIn('Temporary Password', email_obj.body)
        self._assert_qr_attachment(email_obj)

    def test_email_backend_modes(self):
        """Ensure settings can support console (debug) and smtp (prod) modes."""
        # In this test override to console to ensure local tests do not send
        with override_settings(EMAIL_BACKEND='django.core.mail.backends.console.EmailBackend'):
            self.assertEqual(settings.EMAIL_BACKEND, 'django.core.mail.backends.console.EmailBackend')
        # Simulate production choices logic: not asserting creds; just ensure string path
        self.assertTrue(isinstance(settings.EMAIL_BACKEND, str))


