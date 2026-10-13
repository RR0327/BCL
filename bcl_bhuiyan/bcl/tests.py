from datetime import timedelta
from decimal import Decimal
import json

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    IELTSMockTest, ExamModule, ExamSection, Question, QuestionOption,
    CandidateAttempt, CandidateAnswer, WritingEvaluation,
)

User = get_user_model()


class CandidateAuthenticationTests(TestCase):
    def test_registration_page(self):
        self.assertEqual(self.client.get(reverse("bcl:register")).status_code, 200)

    def test_candidate_registration(self):
        response = self.client.post(reverse("bcl:register"), {
            "first_name": "Test", "last_name": "Candidate", "username": "testcandidate",
            "email": "candidate@example.com", "password1": "TestPass@2026abc",
            "password2": "TestPass@2026abc",
        })
        self.assertRedirects(response, reverse("bcl:dashboard"))
        self.assertTrue(User.objects.filter(username="testcandidate").exists())

    def test_duplicate_email_rejected(self):
        User.objects.create_user(username="candidate1", email="candidate@example.com", password="TestPass@2026abc")
        response = self.client.post(reverse("bcl:register"), {
            "first_name": "Second", "last_name": "Candidate", "username": "candidate2",
            "email": "CANDIDATE@example.com", "password1": "TestPass@2026abc",
            "password2": "TestPass@2026abc",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="candidate2").exists())

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse("bcl:dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("bcl:login"), response.url)

    def test_login(self):
        User.objects.create_user(username="candidate", password="TestPass@2026abc")
        response = self.client.post(reverse("bcl:login"), {
            "username": "candidate", "password": "TestPass@2026abc",
        })
        self.assertRedirects(response, reverse("bcl:dashboard"))

    def test_logout(self):
        user = User.objects.create_user(username="candidate", password="TestPass@2026abc")
        self.client.force_login(user)
        self.assertRedirects(self.client.post(reverse("bcl:logout")), reverse("bcl:login"))
        self.assertEqual(self.client.get(reverse("bcl:dashboard")).status_code, 302)

    def test_logout_requires_post(self):
        user = User.objects.create_user(username="candidate", password="TestPass@2026abc")
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("bcl:logout")).status_code, 405)


class IELTSDatabaseTests(TestCase):
    def setUp(self):
        self.candidate = User.objects.create_user(username="ieltscandidate", password="TestPass@2026abc")
        self.examiner = User.objects.create_user(username="examiner", password="TestPass@2026abc", is_staff=True)
        self.mock_test = IELTSMockTest.objects.create(title="IELTS Academic Mock Test 1", test_number=1)
        self.reading = ExamModule.objects.create(mock_test=self.mock_test, module_type="reading", duration_minutes=60)
        self.writing = ExamModule.objects.create(mock_test=self.mock_test, module_type="writing", duration_minutes=60)
        self.section = ExamSection.objects.create(module=self.reading, title="Reading Passage 1", order=1)
        self.question = Question.objects.create(section=self.section, question_type="mcq", question_text="Choose one", correct_answer="B", order=1)
        now = timezone.now()
        self.attempt = CandidateAttempt.objects.create(candidate=self.candidate, module=self.reading, started_at=now, expires_at=now + timedelta(minutes=60))

    def test_mock_test_creation(self):
        self.assertEqual(self.mock_test.test_number, 1)
        self.assertEqual(self.mock_test.modules.count(), 2)

    def test_unique_exam_module(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ExamModule.objects.create(mock_test=self.mock_test, module_type="reading")

    def test_section_and_question_relationship(self):
        self.assertEqual(self.reading.sections.count(), 1)
        self.assertEqual(self.section.questions.count(), 1)

    def test_question_option_creation(self):
        QuestionOption.objects.create(question=self.question, option_key="A", option_text="First", order=1)
        QuestionOption.objects.create(question=self.question, option_key="B", option_text="Second", is_correct=True, order=2)
        self.assertEqual(self.question.options.count(), 2)

    def test_answer_creation(self):
        answer = CandidateAnswer.objects.create(attempt=self.attempt, question=self.question, answer_text="B", is_flagged=True)
        self.assertTrue(answer.is_flagged)

    def test_duplicate_answer_rejected(self):
        CandidateAnswer.objects.create(attempt=self.attempt, question=self.question, answer_text="A")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CandidateAnswer.objects.create(attempt=self.attempt, question=self.question, answer_text="B")

    def test_answer_must_belong_to_module(self):
        section = ExamSection.objects.create(module=self.writing, title="Writing Task 1", order=1)
        question = Question.objects.create(section=section, question_type="essay", question_text="Write", order=1)
        with self.assertRaises(ValidationError):
            CandidateAnswer(attempt=self.attempt, question=question, answer_text="Essay").full_clean()

    def test_invalid_attempt_expiry(self):
        self.attempt.expires_at = self.attempt.started_at - timedelta(seconds=1)
        with self.assertRaises(ValidationError):
            self.attempt.full_clean()

    def test_multiple_attempts_are_allowed(self):
        now = timezone.now()
        CandidateAttempt.objects.create(candidate=self.candidate, module=self.reading, started_at=now, expires_at=now + timedelta(minutes=60))
        self.assertEqual(CandidateAttempt.objects.filter(candidate=self.candidate, module=self.reading).count(), 2)

    def test_writing_evaluation(self):
        now = timezone.now()
        attempt = CandidateAttempt.objects.create(candidate=self.candidate, module=self.writing, started_at=now, expires_at=now + timedelta(minutes=60), status="submitted", submitted_at=now + timedelta(minutes=30))
        evaluation = WritingEvaluation.objects.create(
            attempt=attempt, examiner=self.examiner, task_achievement=Decimal("7.0"),
            coherence_cohesion=Decimal("7.0"), lexical_resource=Decimal("6.5"),
            grammatical_range_accuracy=Decimal("7.0"), feedback="Good organization.",
        )
        evaluation.full_clean()
        self.assertEqual(evaluation.task_achievement, Decimal("7.0"))

    def test_non_writing_attempt_rejects_evaluation(self):
        evaluation = WritingEvaluation(
            attempt=self.attempt, examiner=self.examiner, task_achievement=Decimal("7.0"),
            coherence_cohesion=Decimal("7.0"), lexical_resource=Decimal("7.0"),
            grammatical_range_accuracy=Decimal("7.0"),
        )
        with self.assertRaises(ValidationError):
            evaluation.full_clean()


class ExamSessionTests(TestCase):
    def setUp(self):
        self.candidate = User.objects.create_user(username="sessioncandidate", password="TestPass@2026abc")
        self.other = User.objects.create_user(username="othercandidate", password="TestPass@2026abc")
        self.staff = User.objects.create_user(username="staffuser", password="TestPass@2026abc", is_staff=True)
        self.mock_test = IELTSMockTest.objects.create(title="Exam Engine Test", test_number=20, is_published=True)
        self.module = ExamModule.objects.create(mock_test=self.mock_test, module_type="reading", duration_minutes=60, is_active=True)
        self.section = ExamSection.objects.create(module=self.module, title="First passage", order=1)
        self.question = Question.objects.create(section=self.section, question_type="mcq", question_text="Choose B", order=1)
        QuestionOption.objects.create(question=self.question, option_key="A", option_text="No", order=1)
        QuestionOption.objects.create(question=self.question, option_key="B", option_text="Yes", order=2)
        self.client.force_login(self.candidate)

    def start_attempt(self):
        return self.client.post(reverse("bcl:start_exam", args=[self.module.pk]), {"accept_rules": "yes"})

    def get_attempt(self):
        return CandidateAttempt.objects.filter(candidate=self.candidate, module=self.module).order_by("-pk").first()

    def save(self, attempt, question=None, answer="B", flag=True):
        return self.client.post(
            reverse("bcl:save_exam_answer", args=[attempt.pk]),
            data=json.dumps({"question_id": (question or self.question).pk, "answer_text": answer, "is_flagged": flag}),
            content_type="application/json",
        )

    def test_dashboard_shows_published_test(self):
        self.assertContains(self.client.get(reverse("bcl:dashboard")), "Exam Engine Test")

    def test_rules_page(self):
        self.assertContains(self.client.get(reverse("bcl:exam_rules", args=[self.module.pk])), "Examination Rules")

    def test_start_requires_post(self):
        self.assertEqual(self.client.get(reverse("bcl:start_exam", args=[self.module.pk])).status_code, 405)

    def test_start_requires_rules_acceptance(self):
        self.client.post(reverse("bcl:start_exam", args=[self.module.pk]), {})
        self.assertEqual(CandidateAttempt.objects.count(), 0)

    def test_start_creates_attempt(self):
        response = self.start_attempt()
        attempt = self.get_attempt()
        self.assertRedirects(response, reverse("bcl:exam_session", args=[attempt.pk]))
        self.assertEqual(attempt.status, "in_progress")
        self.assertGreater(attempt.expires_at, attempt.started_at)

    def test_start_resumes_existing_attempt(self):
        self.start_attempt()
        self.start_attempt()
        self.assertEqual(CandidateAttempt.objects.filter(candidate=self.candidate, module=self.module).count(), 1)

    def test_unpublished_test_cannot_start(self):
        self.mock_test.is_published = False
        self.mock_test.save()
        self.assertEqual(self.start_attempt().status_code, 404)

    def test_inactive_module_cannot_start(self):
        self.module.is_active = False
        self.module.save()
        self.assertEqual(self.start_attempt().status_code, 404)

    def test_staff_cannot_start_exam(self):
        self.client.force_login(self.staff)
        self.start_attempt()
        self.assertEqual(CandidateAttempt.objects.count(), 0)

    def test_timer_api(self):
        self.start_attempt()
        response = self.client.get(reverse("bcl:exam_timer", args=[self.get_attempt().pk]))
        self.assertEqual(response.json()["status"], "in_progress")
        self.assertGreater(response.json()["remaining_seconds"], 0)

    def test_other_candidate_cannot_access_attempt(self):
        self.start_attempt()
        attempt = self.get_attempt()
        self.client.force_login(self.other)
        for name in ("exam_session", "exam_timer", "exam_result"):
            self.assertEqual(self.client.get(reverse("bcl:" + name, args=[attempt.pk])).status_code, 404)

    def test_expired_attempt_auto_submits(self):
        self.start_attempt()
        attempt = self.get_attempt()
        attempt.expires_at = timezone.now() - timedelta(seconds=1)
        attempt.save(update_fields=["expires_at"])
        response = self.client.get(reverse("bcl:exam_timer", args=[attempt.pk]))
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, "auto_submitted")
        self.assertEqual(response.json()["remaining_seconds"], 0)

    def test_manual_submission(self):
        self.start_attempt()
        attempt = self.get_attempt()
        response = self.client.post(reverse("bcl:submit_exam", args=[attempt.pk]))
        self.assertRedirects(response, reverse("bcl:exam_result", args=[attempt.pk]))
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, "submitted")

    def test_submission_requires_post(self):
        self.start_attempt()
        self.assertEqual(self.client.get(reverse("bcl:submit_exam", args=[self.get_attempt().pk])).status_code, 405)

    def test_other_candidate_cannot_submit(self):
        self.start_attempt()
        attempt = self.get_attempt()
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(reverse("bcl:submit_exam", args=[attempt.pk])).status_code, 404)

    def test_submitted_attempt_cannot_resume(self):
        self.start_attempt()
        attempt = self.get_attempt()
        self.client.post(reverse("bcl:submit_exam", args=[attempt.pk]))
        self.assertRedirects(self.client.get(reverse("bcl:exam_session", args=[attempt.pk])), reverse("bcl:exam_result", args=[attempt.pk]))

    def test_new_attempt_after_submission(self):
        self.start_attempt()
        first = self.get_attempt()
        self.client.post(reverse("bcl:submit_exam", args=[first.pk]))
        self.start_attempt()
        self.assertEqual(CandidateAttempt.objects.filter(candidate=self.candidate, module=self.module).count(), 2)

    def test_save_answer_and_flag(self):
        self.start_attempt()
        attempt = self.get_attempt()
        response = self.save(attempt)
        self.assertEqual(response.status_code, 200)
        answer = CandidateAnswer.objects.get(attempt=attempt, question=self.question)
        self.assertEqual(answer.answer_text, "B")
        self.assertTrue(answer.is_flagged)

    def test_update_answer_without_duplicate(self):
        self.start_attempt()
        attempt = self.get_attempt()
        self.save(attempt, answer="A", flag=False)
        self.save(attempt, answer="B", flag=True)
        self.assertEqual(CandidateAnswer.objects.filter(attempt=attempt, question=self.question).count(), 1)
        self.assertEqual(CandidateAnswer.objects.get(attempt=attempt).answer_text, "B")

    def test_saved_answers_restored_to_session(self):
        self.start_attempt()
        attempt = self.get_attempt()
        self.save(attempt)
        response = self.client.get(reverse("bcl:exam_session", args=[attempt.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "savedAnswersData")
        self.assertContains(response, '"answer_text": "B"')

    def test_cannot_save_other_modules_question(self):
        self.start_attempt()
        attempt = self.get_attempt()
        writing = ExamModule.objects.create(mock_test=self.mock_test, module_type="writing")
        section = ExamSection.objects.create(module=writing, title="Writing", order=1)
        question = Question.objects.create(section=section, question_type="essay", question_text="Write", order=1)
        self.assertEqual(self.save(attempt, question=question).status_code, 404)

    def test_other_candidate_cannot_save(self):
        self.start_attempt()
        attempt = self.get_attempt()
        self.client.force_login(self.other)
        self.assertEqual(self.save(attempt).status_code, 404)

    def test_cannot_save_after_submission(self):
        self.start_attempt()
        attempt = self.get_attempt()
        self.client.post(reverse("bcl:submit_exam", args=[attempt.pk]))
        self.assertEqual(self.save(attempt).status_code, 409)

    def test_cannot_save_after_expiry(self):
        self.start_attempt()
        attempt = self.get_attempt()
        attempt.expires_at = timezone.now() - timedelta(seconds=1)
        attempt.save(update_fields=["expires_at"])
        self.assertEqual(self.save(attempt).status_code, 409)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, "auto_submitted")

    def test_invalid_mcq_value_rejected(self):
        self.start_attempt()
        self.assertEqual(self.save(self.get_attempt(), answer="Z").status_code, 400)

    def test_invalid_json_rejected(self):
        self.start_attempt()
        response = self.client.post(
            reverse("bcl:save_exam_answer", args=[self.get_attempt().pk]),
            data="not-json", content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_save_requires_post(self):
        self.start_attempt()
        self.assertEqual(self.client.get(reverse("bcl:save_exam_answer", args=[self.get_attempt().pk])).status_code, 405)
