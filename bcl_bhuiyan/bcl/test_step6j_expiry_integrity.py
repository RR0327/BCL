"""Step 6J: expiration is idempotent and follows candidate-first lock order."""
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from bcl.exam_views import expire_attempt_if_needed
from bcl.models import CandidateAttempt, ExamModule, ExamSection, IELTSMockTest, Question


class ExpiryIntegrityTests(TestCase):
    def setUp(self):
        self.candidate = get_user_model().objects.create_user(
            username="step6j_candidate", password="pass"
        )
        self.other = get_user_model().objects.create_user(
            username="step6j_other", password="pass"
        )
        mock = IELTSMockTest.objects.create(
            test_number=27, title="Step 6J", is_published=True
        )
        self.module = ExamModule.objects.create(
            mock_test=mock, module_type="reading", duration_minutes=60
        )
        section = ExamSection.objects.create(
            module=self.module, title="Reading", passage="Original sample"
        )
        Question.objects.create(
            section=section, order=1, question_type="short_answer",
            question_text="What?", correct_answer="Yes"
        )
        now = timezone.now()
        self.attempt = CandidateAttempt.objects.create(
            candidate=self.candidate, module=self.module,
            started_at=now - timedelta(minutes=61),
            expires_at=now - timedelta(minutes=1),
        )
        self.client.force_login(self.candidate)

    def test_expired_timer_closes_attempt_and_sets_timestamp(self):
        response = self.client.get(reverse("bcl:exam_timer", args=[self.attempt.pk]))
        self.assertEqual(response.status_code, 200)
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, CandidateAttempt.AttemptStatus.AUTO_SUBMITTED)
        self.assertIsNotNone(self.attempt.submitted_at)
        self.assertEqual(response.json()["remaining_seconds"], 0)

    def test_expiry_is_idempotent(self):
        with patch("bcl.exam_views.finalize_attempt_score") as finalize:
            expire_attempt_if_needed(self.attempt)
            expire_attempt_if_needed(self.attempt)
        self.assertEqual(finalize.call_count, 1)

    def test_active_attempt_remains_active(self):
        CandidateAttempt.objects.filter(pk=self.attempt.pk).update(
            expires_at=timezone.now() + timedelta(minutes=30)
        )
        refreshed = CandidateAttempt.objects.get(pk=self.attempt.pk)
        with patch("bcl.exam_views.finalize_attempt_score") as finalize:
            updated = expire_attempt_if_needed(refreshed)
        self.assertEqual(updated.status, CandidateAttempt.AttemptStatus.IN_PROGRESS)
        finalize.assert_not_called()

    def test_submitted_attempt_not_rescored(self):
        CandidateAttempt.objects.filter(pk=self.attempt.pk).update(
            status=CandidateAttempt.AttemptStatus.SUBMITTED,
            submitted_at=timezone.now(),
        )
        with patch("bcl.exam_views.finalize_attempt_score") as finalize:
            updated = expire_attempt_if_needed(self.attempt)
        self.assertEqual(updated.status, CandidateAttempt.AttemptStatus.SUBMITTED)
        finalize.assert_not_called()

    def test_other_candidate_cannot_trigger_timer_expiry(self):
        self.client.force_login(self.other)
        response = self.client.get(reverse("bcl:exam_timer", args=[self.attempt.pk]))
        self.assertEqual(response.status_code, 404)
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, CandidateAttempt.AttemptStatus.IN_PROGRESS)

    def test_result_request_expires_attempt(self):
        response = self.client.get(reverse("bcl:exam_result", args=[self.attempt.pk]))
        self.assertEqual(response.status_code, 200)
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, CandidateAttempt.AttemptStatus.AUTO_SUBMITTED)
