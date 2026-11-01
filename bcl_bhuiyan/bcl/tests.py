from .test_helpers import force_verified_staff
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
    CandidateAttempt, CandidateAnswer, WritingEvaluation, WritingTaskEvaluation, FullMockAttempt, CandidateProfile,
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
        self.assertRedirects(response, reverse("bcl:login"))
        user = User.objects.filter(username="testcandidate").first()
        self.assertIsNotNone(user)
        self.assertFalse(user.is_active)
        self.assertEqual(user.candidate_profile.status, CandidateProfile.ApprovalStatus.PENDING)

    def test_candidate_approval_workflow(self):
        self.client.post(reverse("bcl:register"), {
            "first_name": "Approved", "last_name": "Candidate", "username": "approvedcandidate",
            "email": "approved@example.com", "password1": "TestPass@2026abc",
            "password2": "TestPass@2026abc",
        })
        user = User.objects.get(username="approvedcandidate")

        # Try to login before approval -> blocked
        login_res = self.client.post(reverse("bcl:login"), {
            "username": "approvedcandidate", "password": "TestPass@2026abc"
        })
        self.assertEqual(login_res.status_code, 200)
        self.assertContains(login_res, "pending administrator approval")

        # Admin approves user
        admin_user = User.objects.create_superuser(username="adminuser", password="AdminPass@2026abc")
        user.candidate_profile.approve(admin_user=admin_user)
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertEqual(user.candidate_profile.status, CandidateProfile.ApprovalStatus.APPROVED)

        # Now login succeeds and redirects to dashboard
        login_res = self.client.post(reverse("bcl:login"), {
            "username": "approvedcandidate", "password": "TestPass@2026abc"
        })
        self.assertRedirects(login_res, reverse("bcl:dashboard"))

    def test_candidate_rejection_workflow(self):
        self.client.post(reverse("bcl:register"), {
            "first_name": "Rejected", "last_name": "Candidate", "username": "rejectedcandidate",
            "email": "rejected@example.com", "password1": "TestPass@2026abc",
            "password2": "TestPass@2026abc",
        })
        user = User.objects.get(username="rejectedcandidate")
        admin_user = User.objects.create_superuser(username="adminuser2", password="AdminPass@2026abc")
        user.candidate_profile.reject(admin_user=admin_user, reason="Invalid information")
        user.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertEqual(user.candidate_profile.status, CandidateProfile.ApprovalStatus.REJECTED)

        # Login fails with rejection message
        login_res = self.client.post(reverse("bcl:login"), {
            "username": "rejectedcandidate", "password": "TestPass@2026abc"
        })
        self.assertEqual(login_res.status_code, 200)
        self.assertContains(login_res, "rejected by an administrator")

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
        self.assertEqual(response.url, f"{reverse('bcl:login')}?next={reverse('bcl:dashboard')}")

    def test_accounts_login_redirects_to_login(self):
        response = self.client.get("/accounts/login/?next=/dashboard/")
        self.assertRedirects(response, f"{reverse('bcl:login')}?next=/dashboard/", fetch_redirect_response=False)

    def test_accounts_logout_redirects_to_login(self):
        response = self.client.get("/accounts/logout/")
        self.assertRedirects(response, reverse("bcl:login"), fetch_redirect_response=False)

    def test_login(self):
        User.objects.create_user(username="candidate", password="TestPass@2026abc")
        response = self.client.post(reverse("bcl:login"), {
            "username": "candidate", "password": "TestPass@2026abc",
        })
        self.assertRedirects(response, reverse("bcl:dashboard"))

    def test_login_with_next_parameter(self):
        User.objects.create_user(username="candidate_next", password="TestPass@2026abc")
        response = self.client.post(f"{reverse('bcl:login')}?next=/exam/1/rules/", {
            "username": "candidate_next", "password": "TestPass@2026abc",
        })
        self.assertRedirects(response, "/exam/1/rules/", fetch_redirect_response=False)

    def test_logout(self):
        user = User.objects.create_user(username="candidate", password="TestPass@2026abc")
        self.client.force_login(user)
        self.assertRedirects(self.client.post(reverse("bcl:logout")), reverse("bcl:login"))
        dash_response = self.client.get(reverse("bcl:dashboard"))
        self.assertEqual(dash_response.status_code, 302)
        self.assertEqual(dash_response.url, f"{reverse('bcl:login')}?next={reverse('bcl:dashboard')}")

    def test_logout_requires_post(self):
        user = User.objects.create_user(username="candidate_post_logout", password="TestPass@2026abc")
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("bcl:logout")).status_code, 405)

    def test_theme_toggle_elements_present_on_pages(self):
        # 1. Homepage
        home_res = self.client.get(reverse("bcl:home"))
        self.assertEqual(home_res.status_code, 200)
        self.assertContains(home_res, 'id="themeToggleBtn"')
        self.assertContains(home_res, 'theme.')

        # 2. Login
        login_res = self.client.get(reverse("bcl:login"))
        self.assertEqual(login_res.status_code, 200)
        self.assertContains(login_res, 'id="themeToggleBtn"')
        self.assertContains(login_res, 'theme.')

        # 3. Register
        reg_res = self.client.get(reverse("bcl:register"))
        self.assertEqual(reg_res.status_code, 200)
        self.assertContains(reg_res, 'id="themeToggleBtn"')
        self.assertContains(reg_res, 'theme.')

        # 4. Candidate Dashboard
        user = User.objects.create_user(username="candidate_theme", password="TestPass@2026abc")
        self.client.force_login(user)
        dash_res = self.client.get(reverse("bcl:dashboard"))
        self.assertEqual(dash_res.status_code, 200)
        self.assertContains(dash_res, 'id="themeToggleBtn"')
        self.assertContains(dash_res, 'theme.')


class HomeModuleCardTests(TestCase):
    def test_module_cards_do_not_show_question_type_badges(self):
        response = self.client.get(reverse("bcl:home"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "MCQ · TFNG · Matching")
        self.assertNotContains(response, "Audio · Form Fill · MCQ")
        self.assertNotContains(response, "Task 1 &amp; Task 2 Essays")


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
        for name in ("exam_session", "exam_timer", "exam_ended", "exam_result"):
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
        self.assertRedirects(response, reverse("bcl:exam_ended", args=[attempt.pk]))
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, "submitted")

    def test_exam_session_renders_back_button(self):
        self.start_attempt()
        attempt = self.get_attempt()
        response = self.client.get(reverse("bcl:exam_session", args=[attempt.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="headerBackBtn"')
        self.assertContains(response, 'class="back-link')

    def test_dashboard_disables_resume_for_in_progress_listening(self):
        listening_module = ExamModule.objects.create(
            mock_test=self.mock_test, module_type="listening", duration_minutes=30, is_active=True
        )
        CandidateAttempt.objects.create(
            candidate=self.candidate,
            module=listening_module,
            started_at=timezone.now(),
            expires_at=timezone.now() + timedelta(minutes=30),
            status="in_progress",
        )
        response = self.client.get(reverse("bcl:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'disabled title="Listening examinations cannot be resumed."')

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
        self.assertRedirects(self.client.get(reverse("bcl:exam_session", args=[attempt.pk])), reverse("bcl:exam_ended", args=[attempt.pk]))

    def test_exam_ended_in_progress_redirects_to_session(self):
        self.start_attempt()
        attempt = self.get_attempt()
        response = self.client.get(reverse("bcl:exam_ended", args=[attempt.pk]))
        self.assertRedirects(response, reverse("bcl:exam_session", args=[attempt.pk]))

    def test_exam_ended_renders_page_and_links(self):
        self.start_attempt()
        attempt = self.get_attempt()
        self.client.post(reverse("bcl:submit_exam", args=[attempt.pk]))
        response = self.client.get(reverse("bcl:exam_ended", args=[attempt.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Examination Session Ended")
        self.assertContains(response, reverse("bcl:dashboard"))
        self.assertContains(response, reverse("bcl:exam_result", args=[attempt.pk]))
        self.assertContains(response, "Return to Dashboard")
        self.assertContains(response, "View Result")

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


class ExamViolationTests(TestCase):
    """Verify that violations cannot bypass ownership or exam deadlines."""

    def setUp(self):
        self.candidate = User.objects.create_user(username="violation_candidate", password="TestPass@2026abc")
        self.other = User.objects.create_user(username="violation_other", password="TestPass@2026abc")
        self.mock_test = IELTSMockTest.objects.create(title="Violation demo", test_number=88, is_published=True)
        self.module = ExamModule.objects.create(mock_test=self.mock_test, module_type="reading", duration_minutes=60)
        now = timezone.now()
        self.attempt = CandidateAttempt.objects.create(candidate=self.candidate, module=self.module, started_at=now, expires_at=now + timedelta(hours=1))
        self.url = reverse("bcl:report_exam_violation", args=[self.attempt.pk])
        self.client.force_login(self.candidate)

    def report(self, reason="tab_hidden"):
        return self.client.post(self.url, data=json.dumps({"reason": reason}), content_type="application/json")

    def test_first_violation_warns(self):
        response = self.report()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["warning"])
        self.assertFalse(response.json()["auto_submitted"])
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.violation_count, 1)
        self.assertEqual(self.attempt.status, "in_progress")

    def test_second_violation_warns(self):
        self.report()
        response = self.report("window_blur")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["warning"])
        self.assertFalse(response.json()["auto_submitted"])
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.violation_count, 2)
        self.assertEqual(self.attempt.status, "in_progress")

    def test_third_violation_auto_submits(self):
        self.report()
        self.report("window_blur")
        response = self.report("tab_hidden")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["auto_submitted"])
        self.assertFalse(response.json()["warning"])
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.violation_count, 3)
        self.assertEqual(self.attempt.status, "auto_submitted")
        self.assertIsNotNone(self.attempt.submitted_at)

    def test_fourth_report_does_not_increment(self):
        self.report()
        self.report()
        self.report()
        self.assertEqual(self.report().status_code, 409)
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.violation_count, 3)

    def test_other_candidate_cannot_report(self):
        self.client.force_login(self.other)
        self.assertEqual(self.report().status_code, 404)
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.violation_count, 0)

    def test_invalid_payload_does_not_increment(self):
        self.assertEqual(self.report("unknown").status_code, 400)
        self.assertEqual(self.client.post(self.url, data="invalid", content_type="application/json").status_code, 400)
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.violation_count, 0)

    def test_expired_attempt_rejected_and_closed(self):
        self.attempt.expires_at = timezone.now() - timedelta(seconds=1)
        self.attempt.save(update_fields=["expires_at"])
        self.assertEqual(self.report().status_code, 409)
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, "auto_submitted")
        self.assertEqual(self.attempt.violation_count, 0)

    def test_get_not_allowed(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_violation_count_exposed_to_timer(self):
        self.report()
        response = self.client.get(reverse("bcl:exam_timer", args=[self.attempt.pk]))
        self.assertEqual(response.json()["violation_count"], 1)


class ReadingInterfaceTests(TestCase):
    """Reading-specific tools must not affect other module interfaces."""

    def setUp(self):
        self.candidate = User.objects.create_user(username="reading_ui_candidate", password="ExamplePass@2026")
        self.mock_test = IELTSMockTest.objects.create(title="Reading UI test", test_number=99, is_published=True)
        self.reading = ExamModule.objects.create(mock_test=self.mock_test, module_type="reading", duration_minutes=60)
        self.listening = ExamModule.objects.create(mock_test=self.mock_test, module_type="listening", duration_minutes=30)
        for module in (self.reading, self.listening):
            section = ExamSection.objects.create(module=module, title="Section 1", passage="Example passage text.", order=1)
            Question.objects.create(section=section, question_type="fill_blank", question_text="Complete the answer.", order=1)
        self.client.force_login(self.candidate)

    def get_page(self, module):
        now = timezone.now()
        attempt = CandidateAttempt.objects.create(
            candidate=self.candidate, module=module, started_at=now,
            expires_at=now + timedelta(minutes=module.duration_minutes),
        )
        return self.client.get(reverse("bcl:exam_session", args=[attempt.pk]))

    def test_reading_has_highlight_and_notes(self):
        response = self.get_page(self.reading)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="highlight-selection"')
        self.assertContains(response, 'class="passage-notes"')
        self.assertContains(response, 'data-attempt-id=')

    def test_listening_does_not_have_reading_tools(self):
        response = self.get_page(self.listening)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'class="highlight-selection"')
        self.assertNotContains(response, 'class="passage-notes"')


# ==========================================
# PHASE 3 STEP 2 — LISTENING INTERFACE
# ==========================================

class ListeningInterfaceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="listening_candidate", password="TestPass@2026abc"
        )
        self.test = IELTSMockTest.objects.create(
            title="Listening Preview", test_number=29, is_published=True
        )
        self.module = ExamModule.objects.create(
            mock_test=self.test,
            module_type=ExamModule.ModuleType.LISTENING,
            duration_minutes=30, is_active=True
        )
        self.section = ExamSection.objects.create(
            module=self.module, title="Listening Part 1", order=1
        )
        self.question = Question.objects.create(
            section=self.section,
            question_type=Question.QuestionType.SHORT_ANSWER,
            question_text="What is the name?", order=1
        )
        start = timezone.now()
        self.attempt = CandidateAttempt.objects.create(
            candidate=self.user, module=self.module,
            started_at=start, expires_at=start + timedelta(minutes=30)
        )
        self.client.force_login(self.user)

    def test_listening_session_has_player_and_navigation(self):
        response = self.client.get(reverse("bcl:exam_session", args=[self.attempt.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="startListening"')
        self.assertContains(response, 'class="listening-audio-btn state-ready"')
        self.assertContains(response, 'id="listeningAudio"')
        self.assertContains(response, 'data-section-id=')
        self.assertContains(response, "What is the name?")

    def test_reading_audio_player_not_shown(self):
        reading = ExamModule.objects.create(
            mock_test=self.test, module_type=ExamModule.ModuleType.READING,
            duration_minutes=60
        )
        start = timezone.now()
        attempt = CandidateAttempt.objects.create(
            candidate=self.user, module=reading, started_at=start,
            expires_at=start + timedelta(minutes=60)
        )
        response = self.client.get(reverse("bcl:exam_session", args=[attempt.pk]))
        self.assertNotContains(response, 'id="startListening"')

    def test_listening_session_with_continuous_module_audio(self):
        from django.core.files.base import ContentFile
        self.module.audio_file.save("module_master.mp3", ContentFile(b"continuous master audio"), save=True)
        try:
            response = self.client.get(reverse("bcl:exam_session", args=[self.attempt.pk]))
            self.assertEqual(response.status_code, 200)
            expected_url = reverse("bcl:module_media", args=[self.attempt.pk, "audio"])
            self.assertContains(response, f'data-module-audio-url="{expected_url}"')
            self.assertContains(response, "Continuous examination audio (covers all parts)")
        finally:
            self.module.audio_file.delete(save=False)

    def test_listening_session_with_individual_section_audio(self):
        from django.core.files.base import ContentFile
        self.section.audio_file.save("section_part1.mp3", ContentFile(b"section audio"), save=True)
        try:
            response = self.client.get(reverse("bcl:exam_session", args=[self.attempt.pk]))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'data-module-audio-url=""')
            expected_section_url = reverse("bcl:section_media", args=[self.attempt.pk, self.section.pk, "audio"])
            self.assertContains(response, expected_section_url)
        finally:
            self.section.audio_file.delete(save=False)

    def test_listening_session_with_nonexistent_module_audio_file(self):
        """When module.audio_file has a path that doesn't exist on disk, do not emit broken module audio URL."""
        self.module.audio_file.name = "ielts/audio/missing_test_module.mp3"
        self.module.save(update_fields=["audio_file"])
        response = self.client.get(reverse("bcl:exam_session", args=[self.attempt.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-module-audio-url=""')



# ==========================================
# PHASE 3 STEP 3 — WRITING MODULE INTERFACE
# ==========================================

class WritingInterfaceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="writing_candidate", password="TestPass@2026abc"
        )
        self.mock_test = IELTSMockTest.objects.create(
            title="Writing Interface", test_number=78, is_published=True
        )
        self.module = ExamModule.objects.create(
            mock_test=self.mock_test,
            module_type=ExamModule.ModuleType.WRITING,
            duration_minutes=60,
        )
        section = ExamSection.objects.create(
            module=self.module, title="Writing Tasks", order=1,
        )
        self.tasks = []
        for number in (1, 2):
            question = Question.objects.create(
                section=section, question_type=Question.QuestionType.ESSAY,
                question_text=f"Write your Task {number} response.", order=number,
                question_instructions=f"Complete Writing Task {number}.",
            )
            self.tasks.append(question)
        now = timezone.now()
        self.attempt = CandidateAttempt.objects.create(
            candidate=self.user, module=self.module,
            started_at=now, expires_at=now + timedelta(minutes=60)
        )
        self.client.force_login(self.user)

    def test_writing_has_two_separate_editors_and_word_counts(self):
        response = self.client.get(reverse("bcl:exam_session", args=[self.attempt.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="writing-task-split"')
        self.assertContains(response, 'data-task-label="Writing Task 1"')
        self.assertContains(response, 'data-task-label="Writing Task 2"')
        self.assertContains(response, 'id="questionNav"')
        self.assertContains(response, 'id="writingTotalWords"')
        self.assertContains(response, 'class="answer-field writing-editor"', count=2)
        self.assertContains(response, 'Write at least 150 words.')
        self.assertContains(response, 'Write at least 250 words.')
        self.assertContains(response, "Write your Task 1 response.")
        self.assertContains(response, "Write your Task 2 response.")

    def test_writing_tasks_save_separately_and_restore(self):
        for question, response_text in zip(self.tasks, ["First task response", "Second task response"]):
            response = self.client.post(
                reverse("bcl:save_exam_answer", args=[self.attempt.pk]),
                data=json.dumps({
                    "question_id": question.pk,
                    "answer_text": response_text,
                    "is_flagged": False,
                }),
                content_type="application/json",
            )
            self.assertEqual(response.status_code, 200)
        answers = CandidateAnswer.objects.filter(attempt=self.attempt)
        self.assertEqual(answers.count(), 2)
        response = self.client.get(reverse("bcl:exam_session", args=[self.attempt.pk]))
        self.assertContains(response, "First task response")
        self.assertContains(response, "Second task response")

    def test_writing_submission_blocks_further_saves(self):
        self.client.post(reverse("bcl:submit_exam", args=[self.attempt.pk]))
        response = self.client.post(
            reverse("bcl:save_exam_answer", args=[self.attempt.pk]),
            data=json.dumps({
                "question_id": self.tasks[0].pk,
                "answer_text": "Late response",
                "is_flagged": False,
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 409)

# ==========================================
# PHASE 3 STEP 4 — READING / LISTENING SCORING
# ==========================================

class AutoScoringTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="scoring_candidate", password="SafeTestPass2026!")
        self.mock_test = IELTSMockTest.objects.create(title="Scoring test", test_number=101, is_published=True)
        self.module = ExamModule.objects.create(
            mock_test=self.mock_test, module_type="reading", duration_minutes=60
        )
        self.section = ExamSection.objects.create(module=self.module, title="Passage", order=1)
        self.q1 = Question.objects.create(
            section=self.section, question_type="mcq", question_text="Pick B", correct_answer="B", order=1,
        )
        QuestionOption.objects.create(question=self.q1, option_key="A", option_text="Incorrect", order=1)
        QuestionOption.objects.create(question=self.q1, option_key="B", option_text="Correct", is_correct=True, order=2)
        self.q2 = Question.objects.create(
            section=self.section, question_type="fill_blank", question_text="Name a colour", correct_answer="blue||azure", order=2,
        )
        self.now = timezone.now()
        self.attempt = CandidateAttempt.objects.create(
            candidate=self.user, module=self.module, started_at=self.now,
            expires_at=self.now + timedelta(minutes=60),
        )
        self.client.force_login(self.user)

    def test_manual_submission_grades_correct_and_incorrect(self):
        CandidateAnswer.objects.create(attempt=self.attempt, question=self.q1, answer_text="B")
        CandidateAnswer.objects.create(attempt=self.attempt, question=self.q2, answer_text="red")
        self.client.post(reverse("bcl:submit_exam", args=[self.attempt.pk]))
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.raw_score, 1)
        self.assertIsNone(self.attempt.band_score)
        self.assertTrue(CandidateAnswer.objects.get(attempt=self.attempt, question=self.q1).is_correct)
        self.assertFalse(CandidateAnswer.objects.get(attempt=self.attempt, question=self.q2).is_correct)
        response = self.client.get(reverse("bcl:exam_result", args=[self.attempt.pk]))
        self.assertContains(response, "Raw score")
        self.assertContains(response, "1 / 2")

    def test_approved_alternate_answer_matches(self):
        CandidateAnswer.objects.create(attempt=self.attempt, question=self.q2, answer_text=" AZURE ")
        self.client.post(reverse("bcl:submit_exam", args=[self.attempt.pk]))
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.raw_score, 1)

    def test_expiry_grades_at_server_boundary(self):
        CandidateAnswer.objects.create(attempt=self.attempt, question=self.q1, answer_text="B")
        self.attempt.expires_at = timezone.now() - timedelta(seconds=1)
        self.attempt.save(update_fields=["expires_at"])
        self.client.get(reverse("bcl:exam_timer", args=[self.attempt.pk]))
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, "auto_submitted")
        self.assertEqual(self.attempt.raw_score, 1)

    def test_missing_answer_key_blocks_scoring(self):
        self.q2.correct_answer = ""
        self.q2.save(update_fields=["correct_answer"])
        self.client.post(reverse("bcl:submit_exam", args=[self.attempt.pk]))
        self.attempt.refresh_from_db()
        self.assertIsNone(self.attempt.raw_score)

    def test_writing_remains_manual(self):
        writing = ExamModule.objects.create(mock_test=self.mock_test, module_type="writing")
        section = ExamSection.objects.create(module=writing, title="Task 1", order=1)
        q = Question.objects.create(section=section, question_type="essay", question_text="Discuss", order=1)
        now = timezone.now()
        attempt = CandidateAttempt.objects.create(candidate=self.user, module=writing, started_at=now, expires_at=now + timedelta(hours=1))
        CandidateAnswer.objects.create(attempt=attempt, question=q, answer_text="Example essay")
        self.client.post(reverse("bcl:submit_exam", args=[attempt.pk]))
        attempt.refresh_from_db()
        self.assertIsNone(attempt.raw_score)
        self.assertIsNone(attempt.band_score)
        self.assertContains(self.client.get(reverse("bcl:exam_result", args=[attempt.pk])), "manual evaluation")

    def test_full_40_question_band_conversion(self):
        for order in range(3, 41):
            Question.objects.create(
                section=self.section, question_type="short_answer",
                question_text=f"Answer {order}", correct_answer="yes", order=order,
            )
        CandidateAnswer.objects.create(attempt=self.attempt, question=self.q1, answer_text="B")
        self.client.post(reverse("bcl:submit_exam", args=[self.attempt.pk]))
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.raw_score, 1)
        self.assertEqual(self.attempt.band_score, Decimal("1.0"))

    def test_scoring_idempotent_on_repeated_submission(self):
        CandidateAnswer.objects.create(attempt=self.attempt, question=self.q1, answer_text="B")
        endpoint = reverse("bcl:submit_exam", args=[self.attempt.pk])
        self.client.post(endpoint)
        self.client.post(endpoint)
        self.assertEqual(CandidateAnswer.objects.get(attempt=self.attempt, question=self.q1).awarded_marks, 1)
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.raw_score, 1)


# ==========================================
# 4. MANUAL WRITING REVIEW TESTS — PHASE 4
# ==========================================

from .models import WritingTaskEvaluation
from .writing_views import writing_result_band


class WritingReviewTests(TestCase):
    def setUp(self):
        self.candidate = User.objects.create_user(
            username="reviewcandidate", password="TestPass@2026abc",
        )
        self.examiner = User.objects.create_user(
            username="reviewexaminer", password="TestPass@2026abc", is_staff=True,
        )
        self.test = IELTSMockTest.objects.create(title="Writing Review Test", test_number=89)
        self.module = ExamModule.objects.create(
            mock_test=self.test, module_type=ExamModule.ModuleType.WRITING,
        )
        section = ExamSection.objects.create(
            module=self.module, title="Writing Tasks", order=1,
        )
        self.questions = {}
        for n in (1, 2):
            question = Question.objects.create(
                section=section, question_type=Question.QuestionType.ESSAY,
                question_text=f"Task {n} prompt", order=n,
            )
            self.questions[n] = question

        now = timezone.now()
        self.attempt = CandidateAttempt.objects.create(
            candidate=self.candidate, module=self.module,
            started_at=now - timedelta(minutes=60),
            expires_at=now,
            submitted_at=now,
            status=CandidateAttempt.AttemptStatus.SUBMITTED,
        )
        for n in (1, 2):
            CandidateAnswer.objects.create(
                attempt=self.attempt, question=self.questions[n],
                answer_text=f"Candidate essay for task {n}.",
            )
        self.url = reverse("bcl:writing_review_detail", args=[self.attempt.pk])

    def submit_grade(self, task_number, score):
        return self.client.post(self.url, {
            "task_number": str(task_number),
            f"task{task_number}-task_achievement": str(score),
            f"task{task_number}-coherence_cohesion": str(score),
            f"task{task_number}-lexical_resource": str(score),
            f"task{task_number}-grammatical_range_accuracy": str(score),
            f"task{task_number}-feedback": f"Feedback on Task {task_number}",
        })

    def test_nonstaff_cannot_see_review_pages(self):
        self.client.force_login(self.candidate)
        for url in (reverse("bcl:writing_review_list"), self.url):
            self.assertEqual(self.client.get(url).status_code, 302)

    def test_staff_can_read_submission(self):
        force_verified_staff(self.client, self.examiner)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Writing Task 1")
        self.assertContains(response, "Writing Task 2")
        self.assertContains(response, "Candidate essay for task 1")
        self.assertContains(response, "Candidate essay for task 2")

    def test_first_task_only_does_not_publish_band(self):
        force_verified_staff(self.client, self.examiner)
        self.assertRedirects(self.submit_grade(1, "6.0"), self.url)
        self.attempt.refresh_from_db()
        self.assertIsNone(self.attempt.band_score)
        self.assertEqual(self.attempt.task_evaluations.count(), 1)

    def test_both_tasks_publish_weighted_band(self):
        force_verified_staff(self.client, self.examiner)
        self.submit_grade(1, "6.0")
        self.submit_grade(2, "8.0")
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.band_score, Decimal("7.5"))
        self.assertEqual(self.attempt.task_evaluations.count(), 2)
        self.client.force_login(self.candidate)
        response = self.client.get(reverse("bcl:exam_result", args=[self.attempt.pk]))
        self.assertContains(response, "7.5")
        self.assertContains(response, "Feedback on Task 1")

    def test_invalid_score_not_saved(self):
        force_verified_staff(self.client, self.examiner)
        response = self.submit_grade(1, "9.3")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.attempt.task_evaluations.count(), 0)

    def test_regrade_does_not_duplicate_task(self):
        force_verified_staff(self.client, self.examiner)
        self.submit_grade(1, "6.0")
        self.submit_grade(1, "7.0")
        self.assertEqual(self.attempt.task_evaluations.count(), 1)
        self.assertEqual(
            self.attempt.task_evaluations.get(task_number=1).task_achievement,
            Decimal("7.0"),
        )

    def test_other_module_question_is_invalid(self):
        other_module = ExamModule.objects.create(
            mock_test=self.test, module_type=ExamModule.ModuleType.READING,
        )
        section = ExamSection.objects.create(module=other_module, title="Other", order=1)
        question = Question.objects.create(
            section=section, question_type=Question.QuestionType.ESSAY,
            question_text="Unrelated", order=1,
        )
        evaluation = WritingTaskEvaluation(
            attempt=self.attempt, question=question, task_number=1,
            examiner=self.examiner,
            task_achievement=Decimal("6.0"), coherence_cohesion=Decimal("6.0"),
            lexical_resource=Decimal("6.0"), grammatical_range_accuracy=Decimal("6.0"),
        )
        with self.assertRaises(ValidationError):
            evaluation.full_clean()

    def test_in_progress_attempt_cannot_be_graded(self):
        self.attempt.status = CandidateAttempt.AttemptStatus.IN_PROGRESS
        self.attempt.submitted_at = None
        self.attempt.save(update_fields=["status", "submitted_at"])
        force_verified_staff(self.client, self.examiner)
        response = self.client.get(self.url)
        self.assertRedirects(response, reverse("bcl:writing_review_list"))
        self.assertEqual(self.attempt.task_evaluations.count(), 0)


class AllModulesFullMockTests(TestCase):
    def setUp(self):
        self.candidate = User.objects.create_user(username="cand_all_mod", password="TestPass@2026abc")
        self.examiner = User.objects.create_user(username="examiner_all_mod", password="TestPass@2026abc", is_staff=True)
        self.client.force_login(self.candidate)

        self.mock_test = IELTSMockTest.objects.create(
            title="Complete IELTS Mock Test 1",
            test_number=101,
            is_published=True,
        )

        # 1. Reading Module
        self.reading_mod = ExamModule.objects.create(
            mock_test=self.mock_test,
            module_type=ExamModule.ModuleType.READING,
            duration_minutes=60,
            is_active=True,
        )
        sec_r = ExamSection.objects.create(module=self.reading_mod, title="Passage 1", order=1)
        q_r = Question.objects.create(
            section=sec_r,
            question_type=Question.QuestionType.MCQ,
            question_text="Reading Question 1",
            order=1,
            marks=1,
            correct_answer="A",
        )
        QuestionOption.objects.create(question=q_r, option_key="A", option_text="Alpha", order=1)

        # 2. Listening Module
        self.listening_mod = ExamModule.objects.create(
            mock_test=self.mock_test,
            module_type=ExamModule.ModuleType.LISTENING,
            duration_minutes=30,
            is_active=True,
        )
        sec_l = ExamSection.objects.create(module=self.listening_mod, title="Section 1", order=1)
        q_l = Question.objects.create(
            section=sec_l,
            question_type=Question.QuestionType.FILL_BLANK,
            question_text="Listening Question 1",
            order=1,
            marks=1,
            correct_answer="hotel",
        )

        # 3. Writing Module
        self.writing_mod = ExamModule.objects.create(
            mock_test=self.mock_test,
            module_type=ExamModule.ModuleType.WRITING,
            duration_minutes=60,
            is_active=True,
        )
        sec_writing = ExamSection.objects.create(module=self.writing_mod, title="Writing Tasks", order=1)
        self.q_w1 = Question.objects.create(
            section=sec_writing,
            question_type=Question.QuestionType.ESSAY,
            question_text="Summarise the chart",
            order=1,
            marks=3,
        )
        self.q_w2 = Question.objects.create(
            section=sec_writing,
            question_type=Question.QuestionType.ESSAY,
            question_text="Discuss both views",
            order=2,
            marks=6,
        )

    def test_full_mock_rules_requires_all_modules(self):
        # When all 3 modules exist
        response = self.client.get(reverse("bcl:full_mock_rules", args=[self.mock_test.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "All Modules")
        self.assertContains(response, "Reading")
        self.assertContains(response, "Listening")
        self.assertContains(response, "Writing")

        # When a module is inactive or missing
        self.writing_mod.is_active = False
        self.writing_mod.save()
        res_incomplete = self.client.get(reverse("bcl:full_mock_rules", args=[self.mock_test.pk]))
        self.assertRedirects(res_incomplete, reverse("bcl:dashboard"))

    def test_start_full_mock_creates_full_mock_and_listening_attempt(self):
        url = reverse("bcl:start_full_mock", args=[self.mock_test.pk])
        # Requires accepting rules
        res_fail = self.client.post(url, {})
        self.assertRedirects(res_fail, reverse("bcl:full_mock_rules", args=[self.mock_test.pk]))

        # Accept rules starts session
        res_ok = self.client.post(url, {"accept_rules": "yes"})
        full_attempt = FullMockAttempt.objects.get(candidate=self.candidate, mock_test=self.mock_test)
        self.assertEqual(full_attempt.status, FullMockAttempt.AttemptStatus.IN_PROGRESS)
        self.assertEqual(full_attempt.current_step, "listening")
        self.assertIsNotNone(full_attempt.listening_attempt)
        self.assertEqual(full_attempt.listening_attempt.full_mock, full_attempt)
        self.assertEqual(full_attempt.listening_attempt.module.module_type, ExamModule.ModuleType.LISTENING)
        self.assertRedirects(res_ok, reverse("bcl:exam_session", args=[full_attempt.listening_attempt.pk]))

    def test_sequential_full_mock_transitions_to_completion(self):
        # 1. Start full mock -> Listening
        self.client.post(reverse("bcl:start_full_mock", args=[self.mock_test.pk]), {"accept_rules": "yes"})
        full = FullMockAttempt.objects.get(candidate=self.candidate, mock_test=self.mock_test)
        listening_att = full.listening_attempt

        # Save an answer in Listening and submit Listening
        q_l = Question.objects.filter(section__module=self.listening_mod).first()
        self.client.post(
            reverse("bcl:save_exam_answer", args=[listening_att.pk]),
            json.dumps({"question_id": q_l.pk, "answer_text": "hotel", "is_flagged": False}),
            content_type="application/json",
        )
        res_sub_listening = self.client.post(reverse("bcl:submit_exam", args=[listening_att.pk]), {})
        self.assertEqual(res_sub_listening.status_code, 302)
        self.assertEqual(res_sub_listening.url, reverse("bcl:mock_reading", args=[self.mock_test.pk]))

        full.refresh_from_db()
        self.assertEqual(full.current_step, "reading")
        listening_att.refresh_from_db()
        self.assertEqual(listening_att.status, CandidateAttempt.AttemptStatus.SUBMITTED)

        # 2. Continue directly to Reading
        res_launch_reading = self.client.get(reverse("bcl:mock_reading", args=[self.mock_test.pk]))
        full.refresh_from_db()
        self.assertIsNotNone(full.reading_attempt)
        self.assertRedirects(res_launch_reading, reverse("bcl:exam_session", args=[full.reading_attempt.pk]))

        # Submit Reading
        reading_att = full.reading_attempt
        q_r = Question.objects.filter(section__module=self.reading_mod).first()
        self.client.post(
            reverse("bcl:save_exam_answer", args=[reading_att.pk]),
            json.dumps({"question_id": q_r.pk, "answer_text": "A", "is_flagged": False}),
            content_type="application/json",
        )
        res_sub_reading = self.client.post(reverse("bcl:submit_exam", args=[reading_att.pk]), {})
        self.assertEqual(res_sub_reading.status_code, 302)
        self.assertEqual(res_sub_reading.url, reverse("bcl:exam_result", args=[reading_att.pk]))

        full.refresh_from_db()
        self.assertEqual(full.current_step, "writing")

        # 3. Review Reading, then continue to Writing
        res_reading_result = self.client.get(reverse("bcl:exam_result", args=[reading_att.pk]))
        self.assertEqual(res_reading_result.status_code, 200)
        self.assertContains(res_reading_result, "Go to Writing Module")

        res_launch_writing = self.client.get(reverse("bcl:mock_writing", args=[self.mock_test.pk]))
        full.refresh_from_db()
        self.assertIsNotNone(full.writing_attempt)
        self.assertRedirects(res_launch_writing, reverse("bcl:exam_session", args=[full.writing_attempt.pk]))

        # Candidate types answers in Writing and submits
        writing_att = full.writing_attempt
        self.client.post(
            reverse("bcl:save_exam_answer", args=[writing_att.pk]),
            json.dumps({"question_id": self.q_w1.pk, "answer_text": "The provided chart indicates substantial growth in technology.", "is_flagged": False}),
            content_type="application/json",
        )
        res_sub_writing = self.client.post(reverse("bcl:submit_exam", args=[writing_att.pk]), {})
        self.assertRedirects(res_sub_writing, reverse("bcl:full_mock_ended", args=[full.pk]))

        full.refresh_from_db()
        self.assertEqual(full.status, FullMockAttempt.AttemptStatus.SUBMITTED)
        self.assertEqual(full.current_step, "completed")
        partial_result = self.client.get(reverse("bcl:full_mock_result", args=[full.pk]))
        self.assertEqual(partial_result.status_code, 200)
        self.assertTrue(partial_result.context["partial_result"])
        self.assertIsNone(full.reading_attempt)
        self.assertIsNone(full.writing_attempt)

        # 4. View ended page
        res_ended = self.client.get(reverse("bcl:full_mock_ended", args=[full.pk]))
        self.assertEqual(res_ended.status_code, 200)
        self.assertContains(res_ended, "Examination Submitted Successfully")
        self.assertContains(res_ended, "View All Results")

    def test_early_exit_finalizes_full_mock(self):
        # Start full mock at the first required module: Listening
        self.client.post(reverse("bcl:start_full_mock", args=[self.mock_test.pk]), {"accept_rules": "yes"})
        full = FullMockAttempt.objects.get(candidate=self.candidate, mock_test=self.mock_test)
        listening_att = full.listening_attempt

        # Exit full mock via Back button
        res_exit = self.client.post(reverse("bcl:submit_exam", args=[listening_att.pk]), {"exit_full_mock": "true"})
        self.assertRedirects(res_exit, reverse("bcl:full_mock_result", args=[full.pk]))

        full.refresh_from_db()
        self.assertEqual(full.status, FullMockAttempt.AttemptStatus.SUBMITTED)
        self.assertEqual(full.current_step, "completed")

    def test_starting_full_mock_again_creates_fresh_attempt(self):
        self.client.post(reverse("bcl:start_full_mock", args=[self.mock_test.pk]), {"accept_rules": "yes"})
        first = FullMockAttempt.objects.get(candidate=self.candidate, mock_test=self.mock_test)
        listening = first.listening_attempt

        self.client.post(reverse("bcl:submit_exam", args=[listening.pk]), {"exit_full_mock": "true"})
        self.client.post(reverse("bcl:start_full_mock", args=[self.mock_test.pk]), {"accept_rules": "yes"})

        attempts = list(
            FullMockAttempt.objects.filter(candidate=self.candidate, mock_test=self.mock_test)
            .order_by("started_at", "pk")
        )
        self.assertEqual(len(attempts), 2)
        self.assertEqual(attempts[0].status, FullMockAttempt.AttemptStatus.SUBMITTED)
        self.assertEqual(attempts[1].status, FullMockAttempt.AttemptStatus.IN_PROGRESS)
        self.assertNotEqual(attempts[0].pk, attempts[1].pk)
        self.assertEqual(attempts[1].current_step, "listening")
        self.assertEqual(attempts[1].listening_attempt.status, CandidateAttempt.AttemptStatus.IN_PROGRESS)

    def test_full_mock_result_writing_under_review_then_evaluated(self):
        # Create full mock attempt directly with all 3 module attempts submitted
        full = FullMockAttempt.objects.create(
            candidate=self.candidate,
            mock_test=self.mock_test,
            status=FullMockAttempt.AttemptStatus.SUBMITTED,
            current_step="completed",
            submitted_at=timezone.now(),
        )
        r_att = CandidateAttempt.objects.create(
            candidate=self.candidate,
            module=self.reading_mod,
            full_mock=full,
            started_at=timezone.now() - timedelta(minutes=50),
            expires_at=timezone.now() + timedelta(minutes=10),
            submitted_at=timezone.now(),
            status=CandidateAttempt.AttemptStatus.SUBMITTED,
            raw_score=35,
            band_score=Decimal("8.0"),
        )
        l_att = CandidateAttempt.objects.create(
            candidate=self.candidate,
            module=self.listening_mod,
            full_mock=full,
            started_at=timezone.now() - timedelta(minutes=25),
            expires_at=timezone.now() + timedelta(minutes=5),
            submitted_at=timezone.now(),
            status=CandidateAttempt.AttemptStatus.SUBMITTED,
            raw_score=36,
            band_score=Decimal("8.0"),
        )
        w_att = CandidateAttempt.objects.create(
            candidate=self.candidate,
            module=self.writing_mod,
            full_mock=full,
            started_at=timezone.now() - timedelta(minutes=55),
            expires_at=timezone.now() + timedelta(minutes=5),
            submitted_at=timezone.now(),
            status=CandidateAttempt.AttemptStatus.SUBMITTED,
        )
        full.reading_attempt = r_att
        full.listening_attempt = l_att
        full.writing_attempt = w_att
        full.save()

        # Before writing review: shows Under Review and overall band is pending
        res_before = self.client.get(reverse("bcl:full_mock_result", args=[full.pk]))
        self.assertEqual(res_before.status_code, 200)
        self.assertFalse(res_before.context["is_writing_evaluated"])
        self.assertEqual(
            [task["question"].pk for task in res_before.context["writing_tasks"]],
            [self.q_w1.pk, self.q_w2.pk],
        )
        self.assertContains(res_before, "Writing Task 1")
        self.assertContains(res_before, "Writing Task 2")
        self.assertContains(res_before, "Under Review")
        self.assertContains(res_before, "Manual Review Status")

        # Staff evaluates Task 1 and Task 2
        WritingTaskEvaluation.objects.create(
            attempt=w_att,
            question=self.q_w1,
            task_number=1,
            examiner=self.examiner,
            task_achievement=Decimal("7.0"),
            coherence_cohesion=Decimal("7.0"),
            lexical_resource=Decimal("7.0"),
            grammatical_range_accuracy=Decimal("7.0"),
            feedback="Well structured report.",
        )
        WritingTaskEvaluation.objects.create(
            attempt=w_att,
            question=self.q_w2,
            task_number=2,
            examiner=self.examiner,
            task_achievement=Decimal("8.0"),
            coherence_cohesion=Decimal("8.0"),
            lexical_resource=Decimal("8.0"),
            grammatical_range_accuracy=Decimal("8.0"),
            feedback="Excellent essay discussion.",
        )
        from .writing_views import writing_result_band
        w_att.band_score = writing_result_band(w_att)
        w_att.save(update_fields=["band_score"])

        # After writing review: shows Band score and Overall Band
        res_after = self.client.get(reverse("bcl:full_mock_result", args=[full.pk]))
        self.assertEqual(res_after.status_code, 200)
        self.assertTrue(res_after.context["is_writing_evaluated"])
        self.assertContains(res_after, "Overall IELTS Band")
        self.assertContains(res_after, "Well structured report.")
        self.assertContains(res_after, "Excellent essay discussion.")

    def test_dashboard_shows_all_modules_button_and_attempts(self):
        # 1. Available mock tests card has the full-width Full Mock button without star icon
        res = self.client.get(reverse("bcl:dashboard"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Full Mock (150 min)")
        self.assertContains(res, "exam-link-full")
        self.assertNotContains(res, "⭐")
        self.assertContains(res, reverse("bcl:full_mock_rules", args=[self.mock_test.pk]))

        # 2. Add an in-progress full mock attempt
        full = FullMockAttempt.objects.create(
            candidate=self.candidate,
            mock_test=self.mock_test,
            status=FullMockAttempt.AttemptStatus.IN_PROGRESS,
            current_step="reading",
        )
        res_with_att = self.client.get(reverse("bcl:dashboard"))
        self.assertContains(res_with_att, "Full Mock (Listening + Reading + Writing)")
        self.assertContains(res_with_att, "In Progress &bull; Stage: Reading")
        self.assertContains(res_with_att, "Resume")
