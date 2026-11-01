from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import TestCase, RequestFactory
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from .models import (
    IELTSMockTest,
    ExamModule,
    ExamSection,
    Question,
    QuestionOption,
    CandidateAttempt,
    FullMockAttempt,
)
from .admin import (
    IELTSMockTestAdmin,
    ExamModuleAdmin,
    ExamSectionAdmin,
    QuestionAdmin,
    QuestionOptionAdmin,
)
from .test_helpers import force_verified_staff

User = get_user_model()


class MockRequest:
    pass


class AdminUsabilityTests(TestCase):
    def setUp(self):
        self.site = AdminSite()
        self.staff_user = User.objects.create_user(
            username="admin_tester",
            email="admin_tester@example.com",
            password="TestPass@2026abc",
            is_staff=True,
            is_superuser=True,
        )

        self.mock_test = IELTSMockTest.objects.create(
            test_number=99,
            title="Usability Test Exam 1",
            description="Testing usability and question setter ergonomics",
            is_published=True,
        )
        self.module = ExamModule.objects.create(
            mock_test=self.mock_test,
            module_type=ExamModule.ModuleType.READING,
            duration_minutes=60,
        )
        self.section = ExamSection.objects.create(
            module=self.module,
            order=1,
            title="Passage 1: Underwater Archaeology",
            passage="Underwater archaeology explores shipwrecks and submerged ruins.",
            instructions="Questions 1-5: Fill in the blank.",
        )
        self.question = Question.objects.create(
            section=self.section,
            order=1,
            question_type=Question.QuestionType.MCQ,
            question_text="What do archaeologists explore underwater?",
            correct_answer="A",
            marks=1,
        )
        self.option = QuestionOption.objects.create(
            question=self.question,
            option_key="A",
            option_text="Shipwrecks and submerged ruins",
            is_correct=True,
            order=1,
        )

    def test_mock_test_admin_methods(self):
        ma = IELTSMockTestAdmin(IELTSMockTest, self.site)
        overview = ma.modules_overview(self.mock_test)
        self.assertIn("Reading", str(overview))
        total_q = ma.total_questions_count(self.mock_test)
        self.assertIn("1", str(total_q))

    def test_exam_module_admin_methods(self):
        ema = ExamModuleAdmin(ExamModule, self.site)
        link = ema.mock_test_link(self.module)
        self.assertIn("Usability Test Exam 1", str(link))
        badge = ema.module_type_badge(self.module)
        self.assertIn("Reading", str(badge))
        sec_link = ema.sections_link(self.module)
        self.assertIn("1 sections", str(sec_link))

    def test_exam_section_admin_methods(self):
        esa = ExamSectionAdmin(ExamSection, self.site)
        q_link = esa.questions_link(self.section)
        self.assertIn("1 questions", str(q_link))
        passage_badge = esa.has_passage_badge(self.section)
        self.assertIn("words", str(passage_badge))

    def test_question_admin_methods(self):
        qa = QuestionAdmin(Question, self.site)
        short_q = qa.short_question(self.question)
        self.assertIn("archaeologists", short_q)
        q_badge = qa.question_type_badge(self.question)
        self.assertIn("Multiple Choice", str(q_badge))
        opt_sum = qa.options_summary(self.question)
        self.assertIn("1 choices", str(opt_sum))
        ans_preview = qa.correct_answer_preview(self.question)
        self.assertIn("A", str(ans_preview))

    def test_admin_views_http_status(self):
        force_verified_staff(self.client, self.staff_user)

        urls = [
            reverse("admin:bcl_ieltsmocktest_changelist"),
            reverse("admin:bcl_ieltsmocktest_change", args=[self.mock_test.pk]),
            reverse("admin:bcl_exammodule_changelist"),
            reverse("admin:bcl_exammodule_change", args=[self.module.pk]),
            reverse("admin:bcl_examsection_changelist"),
            reverse("admin:bcl_examsection_change", args=[self.section.pk]),
            reverse("admin:bcl_question_changelist"),
            reverse("admin:bcl_question_change", args=[self.question.pk]),
            reverse("admin:bcl_questionoption_changelist"),
            reverse("admin:bcl_questionoption_change", args=[self.option.pk]),
        ]

        for url in urls:
            response = self.client.get(url)
            self.assertEqual(
                response.status_code,
                200,
                f"Failed to load admin URL: {url} (status {response.status_code})",
            )

    def test_mock_test_delete_removes_dependent_attempts(self):
        attempt = CandidateAttempt.objects.create(
            candidate=self.staff_user,
            module=self.module,
            started_at=timezone.now(),
            expires_at=timezone.now() + timedelta(minutes=60),
        )
        full_mock = FullMockAttempt.objects.create(
            candidate=self.staff_user,
            mock_test=self.mock_test,
            listening_attempt=attempt,
        )

        admin_instance = IELTSMockTestAdmin(IELTSMockTest, self.site)
        admin_instance.delete_model(MockRequest(), self.mock_test)

        self.assertFalse(IELTSMockTest.objects.filter(pk=self.mock_test.pk).exists())
        self.assertFalse(CandidateAttempt.objects.filter(pk=attempt.pk).exists())
        self.assertFalse(FullMockAttempt.objects.filter(pk=full_mock.pk).exists())
