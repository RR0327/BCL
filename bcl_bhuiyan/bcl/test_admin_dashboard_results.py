"""Tests for Admin Dashboard, Writing Review redirect, student result view, and PDF/DOCX exports."""
from datetime import timedelta
from io import BytesIO
from zipfile import ZipFile

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    IELTSMockTest,
    ExamModule,
    ExamSection,
    Question,
    QuestionOption,
    CandidateAttempt,
    CandidateAnswer,
    FullMockAttempt,
    WritingEvaluation,
)
from .test_helpers import force_verified_staff


class AdminDashboardAndResultExportTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser("admin_user", "admin@example.com", "pass123")
        self.staff = User.objects.create_user("staff_evaluator", "staff@example.com", "pass123", is_staff=True)
        self.student1 = User.objects.create_user("student_one", "student1@example.com", "pass123")
        self.student2 = User.objects.create_user("student_two", "student2@example.com", "pass123")

        self.mock_test = IELTSMockTest.objects.create(
            test_number=101,
            title="Cambridge IELTS 18 Test 1",
            is_published=True,
        )

        # Reading Module
        self.reading_mod = ExamModule.objects.create(
            mock_test=self.mock_test,
            module_type=ExamModule.ModuleType.READING,
            duration_minutes=60,
            is_active=True,
        )
        sec_r = ExamSection.objects.create(module=self.reading_mod, order=1, title="Reading Passage 1")
        self.q_r = Question.objects.create(section=sec_r, order=1, question_text="Question 1 text", correct_answer="A")

        # Listening Module
        self.listening_mod = ExamModule.objects.create(
            mock_test=self.mock_test,
            module_type=ExamModule.ModuleType.LISTENING,
            duration_minutes=30,
            is_active=True,
        )
        sec_l = ExamSection.objects.create(module=self.listening_mod, order=1, title="Listening Part 1")
        self.q_l = Question.objects.create(section=sec_l, order=1, question_text="Question 1 listening", correct_answer="B")

        # Writing Module
        self.writing_mod = ExamModule.objects.create(
            mock_test=self.mock_test,
            module_type=ExamModule.ModuleType.WRITING,
            duration_minutes=60,
            is_active=True,
        )
        sec_w1 = ExamSection.objects.create(module=self.writing_mod, order=1, title="Writing Task 1")
        self.q_w1 = Question.objects.create(section=sec_w1, order=1, question_type="essay", question_text="Describe the graph.")
        sec_w2 = ExamSection.objects.create(module=self.writing_mod, order=2, title="Writing Task 2")
        self.q_w2 = Question.objects.create(section=sec_w2, order=1, question_type="essay", question_text="Discuss both views.")

        now = timezone.now()
        # Student 1 Reading attempt
        self.reading_att = CandidateAttempt.objects.create(
            candidate=self.student1,
            module=self.reading_mod,
            started_at=now - timedelta(minutes=50),
            submitted_at=now - timedelta(minutes=5),
            expires_at=now + timedelta(minutes=10),
            status=CandidateAttempt.AttemptStatus.SUBMITTED,
            raw_score=35,
            band_score=8.0,
        )
        CandidateAnswer.objects.create(
            attempt=self.reading_att,
            question=self.q_r,
            answer_text="A",
            is_correct=True,
            awarded_marks=1,
        )

        # Student 1 Writing attempt
        self.writing_att = CandidateAttempt.objects.create(
            candidate=self.student1,
            module=self.writing_mod,
            started_at=now - timedelta(minutes=70),
            submitted_at=now - timedelta(minutes=10),
            expires_at=now,
            status=CandidateAttempt.AttemptStatus.SUBMITTED,
        )
        CandidateAnswer.objects.create(
            attempt=self.writing_att,
            question=self.q_w1,
            answer_text="This is an extensive analysis of the Task 1 diagram with more than 150 words.",
        )
        CandidateAnswer.objects.create(
            attempt=self.writing_att,
            question=self.q_w2,
            answer_text="This is a balanced argument regarding education with more than 250 words.",
        )

        # Student 1 Full Mock Attempt
        self.full_mock = FullMockAttempt.objects.create(
            candidate=self.student1,
            mock_test=self.mock_test,
            status=FullMockAttempt.AttemptStatus.SUBMITTED,
            current_step="completed",
            reading_attempt=self.reading_att,
            writing_attempt=self.writing_att,
            started_at=now - timedelta(hours=3),
            submitted_at=now - timedelta(minutes=10),
        )

    def test_admin_dashboard_view_renders_for_staff(self):
        force_verified_staff(self.client, self.admin)
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 200)

        # Check Writing Reviews button redirect link presence
        writing_review_url = reverse("bcl:writing_review_list")
        self.assertIn(writing_review_url, response.content.decode())

        # Check KPI metrics presence
        content = response.content.decode()
        self.assertIn("Registered Students", content)
        self.assertIn("Mock Tests", content)
        self.assertIn("Writing Reviews", content)

        # Check All Student Exam Results hub
        self.assertIn("All Student Exam Results", content)
        self.assertIn("student_one", content)

        # Check export links in dashboard
        pdf_export_url = reverse("bcl:export_candidate_attempt", args=[self.reading_att.pk, "pdf"])
        docx_export_url = reverse("bcl:export_candidate_attempt", args=[self.reading_att.pk, "docx"])
        self.assertIn(pdf_export_url, content)
        self.assertIn(docx_export_url, content)

    def test_staff_can_view_student_individual_result(self):
        force_verified_staff(self.client, self.staff)
        url = reverse("bcl:exam_result", args=[self.reading_att.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Band 8.0", response.content.decode())
        self.assertIn("Cambridge IELTS 18 Test 1", response.content.decode())

    def test_staff_can_view_student_full_mock_result(self):
        force_verified_staff(self.client, self.staff)
        url = reverse("bcl:full_mock_result", args=[self.full_mock.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("student_one", response.content.decode())

    def test_candidate_cannot_view_other_candidate_result(self):
        self.client.force_login(self.student2)
        url = reverse("bcl:exam_result", args=[self.reading_att.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

        fm_url = reverse("bcl:full_mock_result", args=[self.full_mock.pk])
        fm_resp = self.client.get(fm_url)
        self.assertEqual(fm_resp.status_code, 404)

    def test_export_reading_attempt_pdf(self):
        force_verified_staff(self.client, self.staff)
        url = reverse("bcl:export_candidate_attempt", args=[self.reading_att.pk, "pdf"])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))

    def test_export_reading_attempt_docx(self):
        force_verified_staff(self.client, self.staff)
        url = reverse("bcl:export_candidate_attempt", args=[self.reading_att.pk, "docx"])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        with ZipFile(BytesIO(response.content)) as z:
            xml = z.read("word/document.xml").decode("utf-8")
        self.assertIn("Reading", xml)
        self.assertIn("student_one", xml)

    def test_export_writing_attempt_pdf_and_docx(self):
        force_verified_staff(self.client, self.staff)
        # PDF
        pdf_url = reverse("bcl:export_candidate_attempt", args=[self.writing_att.pk, "pdf"])
        pdf_resp = self.client.get(pdf_url)
        self.assertEqual(pdf_resp.status_code, 200)
        self.assertEqual(pdf_resp["Content-Type"], "application/pdf")
        self.assertTrue(pdf_resp.content.startswith(b"%PDF"))

        # DOCX
        docx_url = reverse("bcl:export_candidate_attempt", args=[self.writing_att.pk, "docx"])
        docx_resp = self.client.get(docx_url)
        self.assertEqual(docx_resp.status_code, 200)
        with ZipFile(BytesIO(docx_resp.content)) as z:
            xml = z.read("word/document.xml").decode("utf-8")
        self.assertIn("Writing", xml)
        self.assertIn("Task 1", xml)

    def test_export_full_mock_attempt_pdf_and_docx(self):
        force_verified_staff(self.client, self.staff)
        # PDF
        pdf_url = reverse("bcl:export_full_mock_attempt", args=[self.full_mock.pk, "pdf"])
        pdf_resp = self.client.get(pdf_url)
        self.assertEqual(pdf_resp.status_code, 200)
        self.assertEqual(pdf_resp["Content-Type"], "application/pdf")
        self.assertTrue(pdf_resp.content.startswith(b"%PDF"))

        # DOCX
        docx_url = reverse("bcl:export_full_mock_attempt", args=[self.full_mock.pk, "docx"])
        docx_resp = self.client.get(docx_url)
        self.assertEqual(docx_resp.status_code, 200)
        with ZipFile(BytesIO(docx_resp.content)) as z:
            xml = z.read("word/document.xml").decode("utf-8")
        self.assertIn("Full Mock", xml)
        self.assertIn("student_one", xml)

    def test_candidate_cannot_access_staff_export_endpoints(self):
        self.client.force_login(self.student1)
        url = reverse("bcl:export_candidate_attempt", args=[self.reading_att.pk, "pdf"])
        response = self.client.get(url)
        # Should be redirected by staff_member_required
        self.assertEqual(response.status_code, 302)

        fm_url = reverse("bcl:export_full_mock_attempt", args=[self.full_mock.pk, "pdf"])
        fm_resp = self.client.get(fm_url)
        self.assertEqual(fm_resp.status_code, 302)
