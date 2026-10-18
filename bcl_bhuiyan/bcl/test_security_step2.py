"""Authentication and MFA authorization regressions."""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django_otp.plugins.otp_totp.models import TOTPDevice

class StaffSecurityTests(TestCase):
    def setUp(self):
        U = get_user_model()
        self.staff = U.objects.create_user(username='examiner', password='SafePass123!', is_staff=True)
        self.candidate = U.objects.create_user(username='candidate', password='SafePass123!')

    def test_staff_requires_enrollment(self):
        self.client.force_login(self.staff)
        self.assertRedirects(self.client.get(reverse('bcl:dashboard')), reverse('bcl:mfa_setup'))

    def test_staff_admin_requires_mfa(self):
        self.client.force_login(self.staff)
        self.assertRedirects(self.client.get('/admin/'), reverse('bcl:mfa_setup'))

    def test_staff_with_device_requires_verification(self):
        TOTPDevice.objects.create(user=self.staff, name='primary', confirmed=True)
        self.client.force_login(self.staff)
        self.assertRedirects(self.client.get('/admin/'), reverse('bcl:mfa_verify'))

    def test_candidate_not_forced_to_mfa(self):
        self.client.force_login(self.candidate)
        self.assertEqual(self.client.get(reverse('bcl:dashboard')).status_code, 200)

    def test_candidate_cannot_enroll_staff_mfa(self):
        self.client.force_login(self.candidate)
        self.assertEqual(self.client.get(reverse('bcl:mfa_setup')).status_code, 403)

    def test_anonymous_redirects_to_login(self):
        self.assertEqual(self.client.get(reverse('bcl:mfa_verify')).status_code, 302)

    def test_staff_invalid_code_cannot_pass(self):
        self.client.force_login(self.staff)
        response = self.client.post(reverse('bcl:mfa_setup'), {'token': 'invalid'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(TOTPDevice.objects.filter(user=self.staff, confirmed=True).exists())

    def test_staff_valid_code_enrolls(self):
        self.client.force_login(self.staff)
        self.client.get(reverse('bcl:mfa_setup'))
        device = TOTPDevice.objects.get(user=self.staff)
        from django_otp.oath import totp
        token = str(totp(device.bin_key, step=device.step, t0=device.t0, digits=device.digits)).zfill(device.digits)
        response = self.client.post(reverse('bcl:mfa_setup'), {'token': token})
        self.assertEqual(response.status_code, 302)
        device.refresh_from_db()
        self.assertTrue(device.confirmed)
