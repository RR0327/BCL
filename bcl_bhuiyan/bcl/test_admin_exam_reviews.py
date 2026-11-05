"""
Tests for Admin Exam Results & Reviews Hub, Attempt Reviews (Listening, Reading, Writing),
and Full Mock Reviews with candidate answers vs official correct answers.
"""
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    IELTSMockTest,
    ExamModule,
    ExamSection,
    Question,
    CandidateAttempt,
    CandidateAnswer,
    FullMockAttempt,
    WritingTaskEvaluation,
)
from .test_helpers import force_verified_staff


class AdminExamReviewsTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser("admin_super", "admin@test.com", "pass123")
        self.staff = User.objects.create_user("staff_reviewer", "staff@test.com", "pass123", is_staff=True)
        self.student = User.objects.create_user("student_candidate", "student@test.com", "pass123", first_name="Rahim", last_name="Khan")

        self.mock_test = IELTSMockTest.objects.create(
            test_number=7,
            title="IELTS Academic Mock Test 7",
            is_published=True,
        )

        # 1. Listening Module & Attempt
        self.listening_mod = ExamModule.objects.create(
            mock_test=self.mock_test,
            module_type=ExamModule.ModuleType.LISTENING,
            duration_minutes=30,
            is_active=True,
        )
        now = timezone.now()
        self.listening_att = CandidateAttempt.objects.create(
            candidate=self.student,
            module=self.listening_mod,
            status=CandidateAttempt.AttemptStatus.SUBMITTED,
            started_at=now - timezone.timedelta(minutes=30),
            submitted_at=now,
            expires_at=now + timezone.timedelta(minutes=30),
            raw_score=Decimal("35"),
            band_score=Decimal("8.0"),
            answers_payload={
                "answers": {
                    "1": {"user_answer": "Anthony", "correct_answer": "Anthony", "is_correct": True},
                    "2": {"user_answer": "June 1st", "correct_answer": "1st June / 1 June", "is_correct": True},
                    "3": {"user_answer": "wrong hall", "correct_answer": "University Hall", "is_correct": False},
                }
            }
        )

        # 2. Reading Module & Attempt
        self.reading_mod = ExamModule.objects.create(
            mock_test=self.mock_test,
            module_type=ExamModule.ModuleType.READING,
            duration_minutes=60,
            is_active=True,
        )
        sec_r = ExamSection.objects.create(module=self.reading_mod, order=1, title="Reading Passage 1")
        self.q_r1 = Question.objects.create(
            section=sec_r,
            order=1,
            question_text="What is the main topic of passage 1?",
            question_type=Question.QuestionType.MCQ,
            correct_answer="B",
            explanation="Paragraph 2 explicitly mentions B.",
        )
        self.reading_att = CandidateAttempt.objects.create(
            candidate=self.student,
            module=self.reading_mod,
            status=CandidateAttempt.AttemptStatus.SUBMITTED,
            started_at=now - timezone.timedelta(minutes=55),
            submitted_at=now,
            expires_at=now + timezone.timedelta(minutes=30),
            raw_score=Decimal("32"),
            band_score=Decimal("7.5"),
        )
        CandidateAnswer.objects.create(
            attempt=self.reading_att,
            question=self.q_r1,
            answer_text="B",
            is_correct=True,
        )

        # 3. Writing Module & Attempt
        self.writing_mod = ExamModule.objects.create(
            mock_test=self.mock_test,
            module_type=ExamModule.ModuleType.WRITING,
            duration_minutes=60,
            is_active=True,
        )
        sec_w = ExamSection.objects.create(module=self.writing_mod, order=1, title="Writing Tasks")
        self.q_w1 = Question.objects.create(
            section=sec_w,
            order=1,
            question_text="Summarize the chart below in at least 150 words.",
            question_type=Question.QuestionType.ESSAY,
        )
        self.q_w2 = Question.objects.create(
            section=sec_w,
            order=2,
            question_text="Do advantages of technology outweigh disadvantages?",
            question_type=Question.QuestionType.ESSAY,
        )
        self.writing_att = CandidateAttempt.objects.create(
            candidate=self.student,
            module=self.writing_mod,
            status=CandidateAttempt.AttemptStatus.SUBMITTED,
            started_at=now - timezone.timedelta(minutes=58),
            submitted_at=now,
            expires_at=now + timezone.timedelta(minutes=30),
            raw_score=Decimal("7.0"),
            band_score=Decimal("7.0"),
        )
        CandidateAnswer.objects.create(
            attempt=self.writing_att,
            question=self.q_w1,
            answer_text="The chart illustrates the trends in renewable energy usage between 2000 and 2020...",
        )
        CandidateAnswer.objects.create(
            attempt=self.writing_att,
            question=self.q_w2,
            answer_text="In recent decades, technology has revolutionized every aspect of human life...",
        )
        WritingTaskEvaluation.objects.create(
            attempt=self.writing_att,
            question=self.q_w1,
            examiner=self.staff,
            task_number=1,
            task_achievement=Decimal("7.0"),
            coherence_cohesion=Decimal("7.0"),
            lexical_resource=Decimal("7.5"),
            grammatical_range_accuracy=Decimal("7.0"),
            feedback="Strong overview and well-selected data points.",
        )

        # 4. Full Mock Attempt
        self.full_mock = FullMockAttempt.objects.create(
            candidate=self.student,
            mock_test=self.mock_test,
            status=FullMockAttempt.AttemptStatus.SUBMITTED,
            current_step="completed",
            listening_attempt=self.listening_att,
            reading_attempt=self.reading_att,
            writing_attempt=self.writing_att,
            overall_band_score=Decimal("7.5"),
            started_at=now - timezone.timedelta(hours=3),
            submitted_at=now,
        )

    def test_anonymous_and_candidate_redirected(self):
        # Anonymous
        hub_url = reverse("bcl:admin_results_hub")
        resp = self.client.get(hub_url)
        self.assertEqual(resp.status_code, 302)

        # Candidate
        self.client.force_login(self.student)
        resp2 = self.client.get(hub_url)
        self.assertEqual(resp2.status_code, 302)

        rev_url = reverse("bcl:admin_attempt_review", args=[self.listening_att.pk])
        resp3 = self.client.get(rev_url)
        self.assertEqual(resp3.status_code, 302)

        fm_url = reverse("bcl:admin_full_mock_review", args=[self.full_mock.pk])
        resp4 = self.client.get(fm_url)
        self.assertEqual(resp4.status_code, 302)

    def test_staff_access_admin_results_hub(self):
        force_verified_staff(self.client, self.staff)
        resp = self.client.get(reverse("bcl:admin_results_hub"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Candidate Exam Results &amp; Review Hub")
        self.assertContains(resp, "Rahim Khan")
        self.assertContains(resp, "Band 8.0")
        self.assertContains(resp, "Band 7.5")
        self.assertContains(resp, "IELTS Academic Mock Test 7")

    def test_staff_filter_by_module(self):
        force_verified_staff(self.client, self.staff)

        # Filter: Listening
        resp_l = self.client.get(reverse("bcl:admin_results_hub") + "?module=listening")
        self.assertEqual(resp_l.status_code, 200)
        self.assertContains(resp_l, "Listening")

        # Filter: Reading
        resp_r = self.client.get(reverse("bcl:admin_results_hub") + "?module=reading")
        self.assertEqual(resp_r.status_code, 200)
        self.assertContains(resp_r, "Reading")

        # Filter: Writing
        resp_w = self.client.get(reverse("bcl:admin_results_hub") + "?module=writing")
        self.assertEqual(resp_w.status_code, 200)
        self.assertContains(resp_w, "Writing")

        # Filter: Full Mock
        resp_fm = self.client.get(reverse("bcl:admin_results_hub") + "?module=full_mock")
        self.assertEqual(resp_fm.status_code, 200)
        self.assertContains(resp_fm, "Full Mocks")
        self.assertContains(resp_fm, f"FM #{self.full_mock.pk}")

    def test_staff_search_query(self):
        force_verified_staff(self.client, self.staff)
        # Search by student name
        resp = self.client.get(reverse("bcl:admin_results_hub") + "?q=Rahim")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Rahim Khan")

        # Non-matching search
        resp_none = self.client.get(reverse("bcl:admin_results_hub") + "?q=NonExistentCandidateNameXYZ")
        self.assertEqual(resp_none.status_code, 200)
        self.assertContains(resp_none, "No exam attempts found")

    def test_staff_listening_attempt_review_detail(self):
        force_verified_staff(self.client, self.staff)
        resp = self.client.get(reverse("bcl:admin_attempt_review", args=[self.listening_att.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Listening Review")
        self.assertContains(resp, "Band 8.0")
        self.assertContains(resp, "Rahim Khan")
        # Candidate's answers displayed
        self.assertContains(resp, "Anthony")
        self.assertContains(resp, "June 1st")
        self.assertContains(resp, "wrong hall")
        # Official correct answers displayed
        self.assertContains(resp, "1st June / 1 June")
        self.assertContains(resp, "University Hall")
        # Status indicators
        self.assertContains(resp, "Correct")
        self.assertContains(resp, "Incorrect")

    def test_staff_reading_attempt_review_detail(self):
        force_verified_staff(self.client, self.staff)
        resp = self.client.get(reverse("bcl:admin_attempt_review", args=[self.reading_att.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Reading Review")
        self.assertContains(resp, "Band 7.5")
        self.assertContains(resp, "What is the main topic of passage 1?")
        # Candidate answer and correct answer
        self.assertContains(resp, "B")
        self.assertContains(resp, "Paragraph 2 explicitly mentions B.")

    def test_staff_writing_attempt_review_detail(self):
        force_verified_staff(self.client, self.staff)
        resp = self.client.get(reverse("bcl:admin_attempt_review", args=[self.writing_att.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Writing Review")
        self.assertContains(resp, "Band 7.0")
        self.assertContains(resp, "The chart illustrates the trends")
        self.assertContains(resp, "In recent decades, technology")
        self.assertContains(resp, "Strong overview and well-selected data points.")

    def test_staff_full_mock_review_detail(self):
        force_verified_staff(self.client, self.staff)
        resp = self.client.get(reverse("bcl:admin_full_mock_review", args=[self.full_mock.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Full Mock Review")
        self.assertContains(resp, "Band 7.5")
        self.assertContains(resp, "Overall Band")
        self.assertContains(resp, "Listening Section (40 Qs)")
        self.assertContains(resp, "Reading Section (40 Qs)")
        self.assertContains(resp, "Writing Section (Tasks 1 &amp; 2)")
        # Candidate answers in listening section
        self.assertContains(resp, "Anthony")
        self.assertContains(resp, "University Hall")

    def test_candidate_cannot_delete_writing_result(self):
        self.client.force_login(self.student)
        url = reverse("bcl:writing_review_delete", args=[self.writing_att.pk])
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 302)
        # Verify attempt still exists
        self.assertTrue(CandidateAttempt.objects.filter(pk=self.writing_att.pk).exists())

    def test_get_method_not_allowed_on_delete(self):
        force_verified_staff(self.client, self.staff)
        url = reverse("bcl:writing_review_delete", args=[self.writing_att.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 405)

    def test_staff_delete_writing_result_and_answers(self):
        force_verified_staff(self.client, self.staff)
        writing_id = self.writing_att.pk

        # Check answers and evaluations exist before deletion
        self.assertTrue(CandidateAnswer.objects.filter(attempt_id=writing_id).exists())
        self.assertTrue(WritingTaskEvaluation.objects.filter(attempt_id=writing_id).exists())

        url = reverse("bcl:writing_review_delete", args=[writing_id])
        resp = self.client.post(url, follow=True)
        self.assertEqual(resp.status_code, 200)

        # Verify attempt and all submitted answers and evaluations are permanently wiped from DB
        self.assertFalse(CandidateAttempt.objects.filter(pk=writing_id).exists())
        self.assertFalse(CandidateAnswer.objects.filter(attempt_id=writing_id).exists())
        self.assertFalse(WritingTaskEvaluation.objects.filter(attempt_id=writing_id).exists())

        # Verify FullMock reference is cleared
        self.full_mock.refresh_from_db()
        self.assertIsNone(self.full_mock.writing_attempt)

        # Verify success message rendered
        self.assertContains(resp, f"Writing submission #{writing_id}")
        self.assertContains(resp, "permanently deleted")

    def test_staff_delete_from_admin_tools(self):
        force_verified_staff(self.client, self.staff)
        reading_id = self.reading_att.pk
        url = reverse("bcl:admin_attempt_delete", args=[reading_id])
        resp = self.client.post(url, follow=True)
        self.assertEqual(resp.status_code, 200)

        self.assertFalse(CandidateAttempt.objects.filter(pk=reading_id).exists())
        self.assertFalse(CandidateAnswer.objects.filter(attempt_id=reading_id).exists())
