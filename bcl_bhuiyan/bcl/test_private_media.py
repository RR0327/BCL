from .test_helpers import force_verified_staff
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from .models import IELTSMockTest, ExamModule, ExamSection, CandidateAttempt


class PrivateMediaTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.candidate = User.objects.create_user(username="media_candidate", password="test-pass-123")
        self.other = User.objects.create_user(username="media_other", password="test-pass-123")
        self.staff = User.objects.create_user(username="media_staff", password="test-pass-123", is_staff=True)
        self.test = IELTSMockTest.objects.create(test_number=9991, title="Media access")
        self.module = ExamModule.objects.create(mock_test=self.test, module_type="listening")
        self.other_module = ExamModule.objects.create(mock_test=self.test, module_type="reading")
        self.section = ExamSection.objects.create(module=self.module, title="Part 1", order=1)
        self.section.audio_file.save("sample.mp3", ContentFile(b"test audio"), save=True)
        self.other_section = ExamSection.objects.create(module=self.other_module, title="Other", order=1)
        self.attempt = CandidateAttempt.objects.create(candidate=self.candidate, module=self.module, expires_at=timezone.now()+timedelta(minutes=30))

    def tearDown(self):
        self.section.audio_file.delete(save=False)

    def url(self, section=None, kind="audio"):
        return reverse("bcl:section_media", args=[self.attempt.pk, (section or self.section).pk, kind])

    def test_anonymous_redirected(self):
        self.assertEqual(self.client.get(self.url()).status_code, 302)

    def test_owner_can_stream_without_caching(self):
        self.client.force_login(self.candidate)
        response = self.client.get(self.url())
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(b"".join(response.streaming_content), b"test audio")

    def test_other_candidate_denied(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.url()).status_code, 404)

    def test_staff_denied(self):
        force_verified_staff(self.client, self.staff)
        self.assertEqual(self.client.get(self.url()).status_code, 404)

    def test_cross_module_denied(self):
        self.client.force_login(self.candidate)
        self.assertEqual(self.client.get(self.url(self.other_section)).status_code, 404)

    def test_invalid_kind_denied(self):
        self.client.force_login(self.candidate)
        self.assertEqual(self.client.get(self.url(kind="other")).status_code, 404)

    def test_non_audio_extension_is_not_streamed_as_audio(self):
        self.section.audio_file.name = "ielts/audio/listening-mock.html"
        self.section.save(update_fields=["audio_file"])
        self.client.force_login(self.candidate)
        self.assertEqual(self.client.get(self.url()).status_code, 404)

    def test_submitted_denied(self):
        self.attempt.status = CandidateAttempt.AttemptStatus.SUBMITTED
        self.attempt.save(update_fields=["status"])
        self.client.force_login(self.candidate)
        self.assertEqual(self.client.get(self.url()).status_code, 404)

    def test_expired_denied(self):
        self.attempt.expires_at = timezone.now()-timedelta(seconds=1)
        self.attempt.save(update_fields=["expires_at"])
        self.client.force_login(self.candidate)
        self.assertEqual(self.client.get(self.url()).status_code, 404)
