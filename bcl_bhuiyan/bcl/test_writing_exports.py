from .test_helpers import force_verified_staff
"""Security and content regression tests for Writing report downloads."""
from datetime import timedelta
from io import BytesIO
from zipfile import ZipFile

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import IELTSMockTest, ExamModule, ExamSection, Question, CandidateAttempt, CandidateAnswer
from .result_exports import get_module_attempt_data
from .writing_exports import get_export_data


class WritingExportTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.staff = User.objects.create_user("export_staff", password="example", is_staff=True)
        self.candidate = User.objects.create_user("export_candidate", password="example")
        test = IELTSMockTest.objects.create(test_number=999, title="Export Regression")
        module = ExamModule.objects.create(mock_test=test, module_type="writing")
        section = ExamSection.objects.create(module=module, order=1, title="Writing Tasks")
        now = timezone.now()
        self.attempt = CandidateAttempt.objects.create(
            candidate=self.candidate, module=module, started_at=now-timedelta(hours=1),
            expires_at=now, submitted_at=now, status="submitted")
        for n in (1, 2):
            question = Question.objects.create(section=section, question_type="essay", order=n,
                                               question_text=f"Prompt {n} <example>")
            CandidateAnswer.objects.create(attempt=self.attempt, question=question,
                                           answer_text=f"Essay {n} & special characters")

    def url(self, format, attempt=None):
        return reverse("bcl:writing_export", args=[attempt or self.attempt.pk, format])

    def test_anonymous_cannot_download(self):
        self.assertEqual(self.client.get(self.url("pdf")).status_code, 302)

    def test_single_section_questions_export_as_separate_writing_tasks(self):
        _, writing_tasks, _ = get_export_data(self.attempt.pk)
        self.assertEqual([task["prompt"] for task in writing_tasks], [
            "Prompt 1 <example>", "Prompt 2 <example>",
        ])

        result_data = get_module_attempt_data(self.attempt.pk)
        self.assertEqual(
            [task["prompt"] for task in result_data["writing_tasks"]],
            ["Prompt 1 <example>", "Prompt 2 <example>"],
        )

    def test_candidate_cannot_download(self):
        self.client.force_login(self.candidate)
        self.assertEqual(self.client.get(self.url("docx")).status_code, 302)

    def test_staff_pdf_contains_valid_pdf(self):
        force_verified_staff(self.client, self.staff)
        response = self.client.get(self.url("pdf"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b"%PDF"))
        self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_staff_docx_contains_document(self):
        force_verified_staff(self.client, self.staff)
        response = self.client.get(self.url("docx"))
        self.assertEqual(response.status_code, 200)
        with ZipFile(BytesIO(response.content)) as z:
            xml = z.read("word/document.xml").decode()
        self.assertIn("Essay 1", xml)
        self.assertIn("Essay 2", xml)

    def test_active_attempt_cannot_export(self):
        self.attempt.status = "in_progress"
        self.attempt.submitted_at = None
        self.attempt.save()
        force_verified_staff(self.client, self.staff)
        self.assertEqual(self.client.get(self.url("pdf")).status_code, 404)

    def test_invalid_format_not_found(self):
        force_verified_staff(self.client, self.staff)
        self.assertEqual(self.client.get(self.url("txt")).status_code, 404)

    def test_post_not_allowed(self):
        force_verified_staff(self.client, self.staff)
        self.assertEqual(self.client.post(self.url("pdf")).status_code, 405)
