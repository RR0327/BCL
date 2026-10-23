from decimal import Decimal
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    IELTSMockTest, ExamModule, ExamSection, Question, QuestionOption,
    CandidateAttempt, CandidateAnswer, WritingTaskEvaluation
)
from .scoring import split_alternative_answers, finalize_attempt_score

User = get_user_model()


class AlternativeAnswersAndMediaTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="candidate_review", email="cand_review@example.com", password="Pass#2026Strong"
        )
        self.client.force_login(self.user)

        self.mock_test = IELTSMockTest.objects.create(
            title="VOL-09-T01",
            test_number=9,
            is_published=True,
        )

    def test_split_alternative_answers_utility(self):
        # User specified example: "1st of june / 1st june / first of june / june 1st / june 1 / 1 june"
        text = "1st of june / 1st june / first of june / june 1st / june 1 / 1 june"
        variants = split_alternative_answers(text)
        self.assertEqual(variants, [
            "1st of june", "1st june", "first of june", "june 1st", "june 1", "1 june"
        ])

        # Also supports || and |
        variants_pipe = split_alternative_answers("blue || azure | cyan")
        self.assertEqual(variants_pipe, ["blue", "azure", "cyan"])

    def test_flexible_fill_in_the_blank_scoring(self):
        listening = ExamModule.objects.create(
            mock_test=self.mock_test,
            module_type=ExamModule.ModuleType.LISTENING,
            duration_minutes=30,
        )
        section = ExamSection.objects.create(
            module=listening,
            title="Part 1",
            order=1,
            passage="Transcript for Part 1",
        )
        # Question with multiple acceptable variants separated by /
        q1 = Question.objects.create(
            section=section,
            question_type=Question.QuestionType.FILL_BLANK,
            question_text="Peter wants Jim to move in by [1].",
            correct_answer="1st of june / 1st june / first of june / june 1st / june 1 / 1 june",
            order=1,
            marks=1,
        )
        # Multi-blank question: blank1 has variants; blank2 has variants
        q2 = Question.objects.create(
            section=section,
            question_type=Question.QuestionType.FILL_BLANK,
            question_text="Jim works at a [2] on [3].",
            correct_answer="supermarket / grocery store ;;; Tuesday and Thursday / Tuesdays and Thursdays",
            order=2,
            marks=1,
        )

        now = timezone.now()
        attempt = CandidateAttempt.objects.create(
            candidate=self.user,
            module=listening,
            started_at=now,
            expires_at=now + timedelta(minutes=30),
        )

        # Test candidate answers with different variations:
        # Candidate submits 'june 1st' (one of the valid variants)
        CandidateAnswer.objects.create(attempt=attempt, question=q1, answer_text="june 1st")
        # Candidate submits matching variants for both blanks
        CandidateAnswer.objects.create(
            attempt=attempt, question=q2, answer_text="supermarket ;;; Tuesday and Thursday"
        )

        self.client.post(reverse("bcl:submit_exam", args=[attempt.pk]))
        attempt.refresh_from_db()

        self.assertEqual(attempt.raw_score, 2)
        ans1 = CandidateAnswer.objects.get(attempt=attempt, question=q1)
        self.assertTrue(ans1.is_correct)
        self.assertEqual(ans1.awarded_marks, 1)

        ans2 = CandidateAnswer.objects.get(attempt=attempt, question=q2)
        self.assertTrue(ans2.is_correct)
        self.assertEqual(ans2.awarded_marks, 1)

    def test_question_with_image_and_table_content(self):
        reading = ExamModule.objects.create(
            mock_test=self.mock_test,
            module_type=ExamModule.ModuleType.READING,
            duration_minutes=60,
        )
        section = ExamSection.objects.create(
            module=reading,
            title="Passage 1",
            order=1,
            passage="Passage reading text",
        )

        dummy_png = SimpleUploadedFile(
            name="diagram.png",
            content=b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82",
            content_type="image/png",
        )
        table_html = (
            "<table class='table'><tr><th>Year</th><th>Production</th></tr>"
            "<tr><td>2020</td><td>10,000</td></tr></table>"
        )

        q = Question.objects.create(
            section=section,
            question_type=Question.QuestionType.SHORT_ANSWER,
            question_text="Refer to the figure and table above to find production.",
            correct_answer="10,000 / 10000",
            image=dummy_png,
            table_content=table_html,
            order=1,
            marks=1,
        )

        self.assertTrue(q.image)
        self.assertIn("Production", q.table_content)

        now = timezone.now()
        attempt = CandidateAttempt.objects.create(
            candidate=self.user,
            module=reading,
            started_at=now,
            expires_at=now + timedelta(minutes=60),
        )

        # 1. Exam session view renders image and table
        session_res = self.client.get(reverse("bcl:exam_session", args=[attempt.pk]))
        self.assertEqual(session_res.status_code, 200)
        self.assertContains(session_res, "Production")
        self.assertContains(session_res, reverse("bcl:question_media", args=[attempt.pk, q.pk]))

        # Candidate submits
        CandidateAnswer.objects.create(attempt=attempt, question=q, answer_text="10000")
        self.client.post(reverse("bcl:submit_exam", args=[attempt.pk]))

        # 2. Result review view renders image, table, correct arrow, and explanation
        result_res = self.client.get(reverse("bcl:exam_result", args=[attempt.pk]))
        self.assertEqual(result_res.status_code, 200)
        self.assertContains(result_res, "Production")
        self.assertContains(result_res, reverse("bcl:review_question_media", args=[attempt.pk, q.pk]))
        self.assertContains(result_res, "10,000 / 10000")

    def test_writing_review_dashboard_and_result(self):
        writing = ExamModule.objects.create(
            mock_test=self.mock_test,
            module_type=ExamModule.ModuleType.WRITING,
            duration_minutes=60,
        )
        sec1 = ExamSection.objects.create(module=writing, title="Task 1", order=1)
        sec2 = ExamSection.objects.create(module=writing, title="Task 2", order=2)
        q1 = Question.objects.create(
            section=sec1, question_type=Question.QuestionType.ESSAY,
            question_text="Summarise the report", order=1
        )
        q2 = Question.objects.create(
            section=sec2, question_type=Question.QuestionType.ESSAY,
            question_text="Discuss both views", order=1
        )

        now = timezone.now()
        attempt = CandidateAttempt.objects.create(
            candidate=self.user,
            module=writing,
            started_at=now,
            expires_at=now + timedelta(minutes=60),
        )

        CandidateAnswer.objects.create(attempt=attempt, question=q1, answer_text="My Task 1 response essay")
        CandidateAnswer.objects.create(attempt=attempt, question=q2, answer_text="My Task 2 response essay")
        self.client.post(reverse("bcl:submit_exam", args=[attempt.pk]))

        # Before evaluation: Dashboard displays Writing Under Review
        dash_res = self.client.get(reverse("bcl:dashboard"))
        self.assertEqual(dash_res.status_code, 200)
        self.assertContains(dash_res, "Writing Under Review")

        # Result page shows pending manual evaluation notice
        res1 = self.client.get(reverse("bcl:exam_result", args=[attempt.pk]))
        self.assertContains(res1, "Writing Evaluation Pending")
        self.assertContains(res1, "manual evaluation")

        # Now examiner grades Task 1 and Task 2
        examiner = User.objects.create_superuser("examiner_rev", "ex@example.com", "Pass#2026Examiner")
        WritingTaskEvaluation.objects.create(
            attempt=attempt, question=q1, task_number=1, examiner=examiner,
            task_achievement=Decimal("7.0"), coherence_cohesion=Decimal("7.0"),
            lexical_resource=Decimal("7.0"), grammatical_range_accuracy=Decimal("7.0"),
            feedback="Good summary of Task 1",
        )
        WritingTaskEvaluation.objects.create(
            attempt=attempt, question=q2, task_number=2, examiner=examiner,
            task_achievement=Decimal("8.0"), coherence_cohesion=Decimal("8.0"),
            lexical_resource=Decimal("8.0"), grammatical_range_accuracy=Decimal("8.0"),
            feedback="Strong essay argument for Task 2",
        )
        # Weighting: 1/3 Task 1 + 2/3 Task 2 = (7 + 16)/3 = 7.666 -> rounds to 7.5
        attempt.band_score = Decimal("7.5")
        attempt.save(update_fields=["band_score"])

        # Candidate reviews evaluated writing in dashboard
        dash_eval = self.client.get(reverse("bcl:dashboard"))
        self.assertContains(dash_eval, "Band 7.5")
        self.assertContains(dash_eval, "Evaluated")
        self.assertContains(dash_eval, "Review Feedback")

        # Candidate reviews detailed result page
        result_eval = self.client.get(reverse("bcl:exam_result", args=[attempt.pk]))
        self.assertEqual(result_eval.status_code, 200)
        self.assertContains(result_eval, "Practice Band 7.5")
        self.assertContains(result_eval, "Good summary of Task 1")
        self.assertContains(result_eval, "Strong essay argument for Task 2")
        self.assertContains(result_eval, "Task Achievement")
        self.assertContains(result_eval, "Coherence & Cohesion")
