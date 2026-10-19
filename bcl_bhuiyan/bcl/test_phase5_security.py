from .test_helpers import force_verified_staff
"""Phase 5 Step 3 security and deployment regression tests."""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from .models import IELTSMockTest, ExamModule, CandidateAttempt

class ProductionConfigurationTests(SimpleTestCase):
    def test_session_cookie_is_httponly(self):
        self.assertTrue(settings.SESSION_COOKIE_HTTPONLY)
    def test_csrf_cookie_is_httponly(self):
        self.assertTrue(settings.CSRF_COOKIE_HTTPONLY)
    def test_frame_ancestors_protected(self):
        self.assertEqual(settings.X_FRAME_OPTIONS, 'DENY')
    def test_content_type_sniffing_disabled(self):
        self.assertTrue(settings.SECURE_CONTENT_TYPE_NOSNIFF)
    def test_staticfiles_storage_configured(self):
        self.assertIn('whitenoise', settings.STORAGES['staticfiles']['BACKEND'])
    def test_no_public_media_route_when_debug_false(self):
        from bcl_bhuiyan.urls import urlpatterns
        self.assertFalse(any(str(p.pattern).startswith('media/') for p in urlpatterns)) if not settings.DEBUG else None

class AuthorizationSecurityTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.candidate = User.objects.create_user('candidate_security', password='test-password-strong')
        self.other = User.objects.create_user('other_security', password='test-password-strong')
        self.staff = User.objects.create_user('staff_security', password='test-password-strong', is_staff=True)
        self.test = IELTSMockTest.objects.create(test_number=28, title='Security practice')
        self.module = ExamModule.objects.create(mock_test=self.test, module_type='writing')
        from django.utils import timezone
        from datetime import timedelta
        now = timezone.now()
        self.attempt = CandidateAttempt.objects.create(candidate=self.candidate, module=self.module,
            started_at=now, expires_at=now+timedelta(minutes=60), status='submitted', submitted_at=now)
    def test_anonymous_cannot_download_writing_export(self):
        response = self.client.get(reverse('bcl:writing_export', args=[self.attempt.pk, 'pdf']))
        self.assertEqual(response.status_code, 302)
    def test_candidate_cannot_download_writing_export(self):
        self.client.force_login(self.candidate)
        response = self.client.get(reverse('bcl:writing_export', args=[self.attempt.pk, 'pdf']))
        self.assertEqual(response.status_code, 302)
    def test_other_candidate_cannot_access_result(self):
        self.client.force_login(self.other)
        response = self.client.get(reverse('bcl:exam_result', args=[self.attempt.pk]))
        self.assertEqual(response.status_code, 404)
    def test_invalid_export_extension_is_rejected(self):
        force_verified_staff(self.client, self.staff)
        response = self.client.get(reverse('bcl:writing_export', args=[self.attempt.pk, 'html']))
        self.assertEqual(response.status_code, 404)
    def test_export_has_private_no_store_header(self):
        force_verified_staff(self.client, self.staff)
        response = self.client.get(reverse('bcl:writing_export', args=[self.attempt.pk, 'docx']))
        self.assertEqual(response.status_code, 200)
        self.assertIn('no-store', response['Cache-Control'])
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
