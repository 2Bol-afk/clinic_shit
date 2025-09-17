from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from django.utils import timezone
from .models import Patient
import json

class QRScanAPITest(TestCase):
    def setUp(self):
        # Create a test patient
        self.patient = Patient.objects.create(
            full_name="Test Patient",
            email="test@example.com",
            contact="1234567890",
            address="Test Address",
            age=25,
            patient_code="TEST123"
        )
        
    def test_qr_scan_api_success(self):
        """Test QR scan API returns patient data successfully"""
        response = self.client.get('/patients/api/qr-scan/', {'email': 'test@example.com'})
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.content)
        self.assertTrue(data['success'])
        self.assertEqual(data['patient']['full_name'], 'Test Patient')
        self.assertEqual(data['patient']['email'], 'test@example.com')
        self.assertEqual(data['patient']['patient_code'], 'TEST123')
        
    def test_qr_scan_api_invalid_email(self):
        """Test QR scan API handles invalid email format"""
        response = self.client.get('/patients/api/qr-scan/', {'email': 'invalid-email'})
        self.assertEqual(response.status_code, 400)
        
        data = json.loads(response.content)
        self.assertIn('error', data)
        self.assertEqual(data['error_type'], 'invalid_format')
        
    def test_qr_scan_api_patient_not_found(self):
        """Test QR scan API handles non-existent patient"""
        response = self.client.get('/patients/api/qr-scan/', {'email': 'nonexistent@example.com'})
        self.assertEqual(response.status_code, 404)
        
        data = json.loads(response.content)
        self.assertIn('error', data)
        self.assertEqual(data['error_type'], 'not_found')

class AuthenticationBackendTest(TestCase):
    def setUp(self):
        # Create a test user
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
    def test_email_authentication(self):
        """Test authentication with email address"""
        user = authenticate(username='test@example.com', password='testpass123')
        self.assertIsNotNone(user)
        self.assertEqual(user, self.user)
        
    def test_username_authentication(self):
        """Test authentication with username"""
        user = authenticate(username='testuser', password='testpass123')
        self.assertIsNotNone(user)
        self.assertEqual(user, self.user)
        
    def test_invalid_credentials(self):
        """Test authentication with invalid credentials"""
        user = authenticate(username='test@example.com', password='wrongpassword')
        self.assertIsNone(user)
        
    def test_nonexistent_user(self):
        """Test authentication with nonexistent user"""
        user = authenticate(username='nonexistent@example.com', password='testpass123')
        self.assertIsNone(user)

class PatientRedirectTest(TestCase):
    def setUp(self):
        # Create a test patient with linked user
        self.user = User.objects.create_user(
            username='testpatient',
            email='patient@example.com',
            password='testpass123'
        )
        self.patient = Patient.objects.create(
            full_name='Test Patient',
            email='patient@example.com',
            contact='1234567890',
            address='Test Address',
            age=25,
            patient_code='TEST123',
            user=self.user
        )
        # Add to Patient group
        from django.contrib.auth.models import Group
        patient_group, _ = Group.objects.get_or_create(name='Patient')
        self.user.groups.add(patient_group)
        
    def test_patient_login_redirect(self):
        """Test that patient users are redirected to patient portal"""
        from django.test import Client
        from django.urls import reverse
        
        client = Client()
        response = client.post('/accounts/login/', {
            'username': 'patient@example.com',
            'password': 'testpass123'
        }, follow=True)
        
        # Should redirect to patient portal
        self.assertRedirects(response, '/patients/portal/', status_code=302, target_status_code=200)

class QRScanWorkflowTest(TestCase):
    def setUp(self):
        # Create a test patient with linked user
        self.user = User.objects.create_user(
            username='testpatient',
            email='patient@example.com',
            password='testpass123'
        )
        self.patient = Patient.objects.create(
            full_name='Test Patient',
            email='patient@example.com',
            contact='1234567890',
            address='Test Address',
            age=25,
            patient_code='TEST123',
            user=self.user
        )
        # Add to Patient group
        from django.contrib.auth.models import Group
        patient_group, _ = Group.objects.get_or_create(name='Patient')
        self.user.groups.add(patient_group)
        
    def test_qr_scan_api_validation(self):
        """Test QR scan API validates patients correctly"""
        response = self.client.get('/patients/api/qr-scan/', {'email': 'patient@example.com'})
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.content)
        self.assertTrue(data['success'])
        self.assertEqual(data['patient']['email'], 'patient@example.com')
        
    def test_qr_scan_api_invalid_patient(self):
        """Test QR scan API handles invalid patients"""
        response = self.client.get('/patients/api/qr-scan/', {'email': 'nonexistent@example.com'})
        self.assertEqual(response.status_code, 404)
        
        data = json.loads(response.content)
        self.assertIn('error', data)
        
    def test_qr_login_auto_authentication(self):
        """Test QR login auto-authenticates valid patients"""
        from django.test import Client
        
        client = Client()
        response = client.post('/patients/qr-login/', {
            'email': 'patient@example.com'
        }, follow=True)
        
        # Should redirect to patient portal after auto-login
        self.assertRedirects(response, '/patients/portal/', status_code=302, target_status_code=200)

class DoctorVerificationTest(TestCase):
    def setUp(self):
        # Create a test patient
        self.patient = Patient.objects.create(
            full_name='Test Patient',
            email='patient@example.com',
            contact='1234567890',
            address='Test Address',
            age=25,
            patient_code='TEST123'
        )
        
        # Create a test doctor
        self.doctor_user = User.objects.create_user(
            username='doctor',
            email='doctor@example.com',
            password='testpass123'
        )
        from django.contrib.auth.models import Group
        doctor_group, _ = Group.objects.get_or_create(name='Doctor')
        self.doctor_user.groups.add(doctor_group)
        
    def test_verification_qr_scan_api(self):
        """Test QR scan API works for verification"""
        response = self.client.get('/patients/api/qr-scan/', {'email': 'patient@example.com'})
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.content)
        self.assertTrue(data['success'])
        self.assertEqual(data['patient']['email'], 'patient@example.com')
        
    def test_verification_invalid_patient(self):
        """Test verification with invalid patient"""
        response = self.client.get('/patients/api/qr-scan/', {'email': 'nonexistent@example.com'})
        self.assertEqual(response.status_code, 404)
        
        data = json.loads(response.content)
        self.assertIn('error', data)

class DoctorVerificationWorkflowTest(TestCase):
    def setUp(self):
        # Create a test patient
        self.patient = Patient.objects.create(
            full_name='Test Patient',
            email='patient@example.com',
            contact='1234567890',
            address='Test Address',
            age=25,
            patient_code='TEST123'
        )
        
        # Create a test doctor
        self.doctor_user = User.objects.create_user(
            username='doctor',
            email='doctor@example.com',
            password='testpass123'
        )
        from django.contrib.auth.models import Group
        doctor_group, _ = Group.objects.get_or_create(name='Doctor')
        self.doctor_user.groups.add(doctor_group)
        
        # Create a reception visit that's been claimed
        from visits.models import Visit
        self.visit = Visit.objects.create(
            patient=self.patient,
            service='reception',
            claimed_by=self.doctor_user,
            claimed_at=timezone.now()
        )
        
    def test_doctor_verify_arrival_with_email(self):
        """Test doctor verification with email-based QR scan"""
        from django.test import Client
        
        client = Client()
        client.force_login(self.doctor_user)
        
        response = client.post('/dashboard/doctors/verify/', {
            'reception_visit_id': self.visit.id,
            'patient_email': 'patient@example.com'
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data['success'])
        self.assertEqual(data['message'], 'Patient verified! Status updated to Ready to Consult.')
        
        # Check that the visit status was updated
        self.visit.refresh_from_db()
        self.assertTrue(self.visit.doctor_arrived)
        self.assertEqual(self.visit.doctor_status, 'ready_to_consult')
        
    def test_doctor_verify_arrival_invalid_patient(self):
        """Test doctor verification with invalid patient email"""
        from django.test import Client
        
        client = Client()
        client.force_login(self.doctor_user)
        
        response = client.post('/dashboard/doctors/verify/', {
            'reception_visit_id': self.visit.id,
            'patient_email': 'invalid@example.com'
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertFalse(data['success'])
        self.assertIn('Invalid patient QR', data['message'])
        
    def test_doctor_verify_arrival_wrong_patient(self):
        """Test doctor verification with wrong patient email"""
        from django.test import Client
        
        # Create another patient
        other_patient = Patient.objects.create(
            full_name='Other Patient',
            email='other@example.com',
            contact='1234567890',
            address='Other Address',
            age=30,
            patient_code='OTHER123'
        )
        
        client = Client()
        client.force_login(self.doctor_user)
        
        response = client.post('/dashboard/doctors/verify/', {
            'reception_visit_id': self.visit.id,
            'patient_email': 'other@example.com'
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertFalse(data['success'])
        self.assertIn('Invalid patient QR', data['message'])
