"""Step 6I: superseded candidate sessions cannot masquerade as live exams."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from bcl.models import CandidateAttempt, ExamModule, ExamSection, IELTSMockTest, Question


class CandidateReadIntegrityTests(TestCase):
    def setUp(self):
        self.candidate = get_user_model().objects.create_user(username="step6i_candidate", password="pass")
        self.other = get_user_model().objects.create_user(username="step6i_other", password="pass")
        mock = IELTSMockTest.objects.create(test_number=28, title="Step 6I", is_published=True)
        self.module = ExamModule.objects.create(mock_test=mock, module_type="reading", duration_minutes=60)
        section = ExamSection.objects.create(module=self.module, title="Reading", passage="Original sample")
        Question.objects.create(section=section, order=1, question_type="short_answer", question_text="What?", correct_answer="Yes")
        now = timezone.now()
        self.old = CandidateAttempt.objects.create(candidate=self.candidate, module=self.module,
            started_at=now - timedelta(minutes=3), expires_at=now + timedelta(minutes=57))
        self.new = CandidateAttempt.objects.create(candidate=self.candidate, module=self.module,
            started_at=now - timedelta(minutes=2), expires_at=now + timedelta(minutes=58))
        self.client.force_login(self.candidate)

    def test_superseded_session_redirects_to_rules(self):
        response = self.client.get(reverse("bcl:exam_session", args=[self.old.pk]))
        self.assertRedirects(response, reverse("bcl:exam_rules", args=[self.module.pk]), fetch_redirect_response=False)

    def test_superseded_timer_returns_conflict_and_no_remaining_time(self):
        response = self.client.get(reverse("bcl:exam_timer", args=[self.old.pk]))
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["status"], "superseded")
        self.assertEqual(response.json()["remaining_seconds"], 0)

    def test_newest_timer_stays_active(self):
        response = self.client.get(reverse("bcl:exam_timer", args=[self.new.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertGreater(response.json()["remaining_seconds"], 0)

    def test_newest_session_stays_accessible(self):
        response = self.client.get(reverse("bcl:exam_session", args=[self.new.pk]))
        self.assertEqual(response.status_code, 200)

    def test_other_candidate_cannot_read_session_or_timer(self):
        self.client.force_login(self.other)
        for name in ("bcl:exam_session", "bcl:exam_timer"):
            self.assertEqual(self.client.get(reverse(name, args=[self.new.pk])).status_code, 404)

    def test_expired_session_timer_auto_submits(self):
        CandidateAttempt.objects.filter(pk=self.new.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        response = self.client.get(reverse("bcl:exam_timer", args=[self.new.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["remaining_seconds"], 0)
        self.new.refresh_from_db()
        self.assertEqual(self.new.status, CandidateAttempt.AttemptStatus.AUTO_SUBMITTED)

    def test_closed_session_timer_returns_zero(self):
        CandidateAttempt.objects.filter(pk=self.new.pk).update(
            status=CandidateAttempt.AttemptStatus.SUBMITTED, submitted_at=timezone.now())
        response = self.client.get(reverse("bcl:exam_timer", args=[self.new.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["remaining_seconds"], 0)
