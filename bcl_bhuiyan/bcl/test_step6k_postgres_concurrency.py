"""Step 6K: real-transaction PostgreSQL concurrency regression checks.

These tests deliberately use TransactionTestCase rather than TestCase: a TestCase
outer transaction can hide locking defects and cannot be shared by workers.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from django.test import Client, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from bcl.models import CandidateAttempt, ExamModule, ExamSection, IELTSMockTest, Question


class PostgreSQLCandidateConcurrencyTests(TransactionTestCase):
    databases = {"default"}

    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("Real PostgreSQL row locking is required")
        self.candidate = get_user_model().objects.create_user(
            username="step6k_candidate", password="test-only-password"
        )
        mock = IELTSMockTest.objects.create(
            test_number=29, title="Step 6K concurrency", is_published=True
        )
        self.module = ExamModule.objects.create(
            mock_test=mock, module_type="reading", duration_minutes=60
        )
        section = ExamSection.objects.create(
            module=self.module, title="Sample section", passage="Sample passage"
        )
        self.question = Question.objects.create(
            section=section, order=1, question_type="short_answer",
            question_text="State a sample answer", correct_answer="sample"
        )

    def _parallel_requests(self, operations):
        barrier = Barrier(len(operations))

        def run(operation):
            close_old_connections()
            try:
                client = Client()
                client.force_login(self.candidate)
                barrier.wait(timeout=15)
                return operation(client)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=len(operations)) as executor:
            futures = [executor.submit(run, operation) for operation in operations]
            return [future.result(timeout=30) for future in futures]

    def test_two_simultaneous_starts_create_one_active_attempt(self):
        url = reverse("bcl:start_exam", args=[self.module.pk])
        results = self._parallel_requests([
            lambda client: client.post(url, {"accept_rules": "yes"}),
            lambda client: client.post(url, {"accept_rules": "yes"}),
        ])
        self.assertEqual([r.status_code for r in results], [302, 302])
        active = CandidateAttempt.objects.filter(
            candidate=self.candidate, module=self.module,
            status=CandidateAttempt.AttemptStatus.IN_PROGRESS,
        )
        self.assertEqual(active.count(), 1)
        self.assertEqual(results[0]["Location"], results[1]["Location"])

    def test_parallel_submissions_finalize_only_once(self):
        now = timezone.now()
        attempt = CandidateAttempt.objects.create(
            candidate=self.candidate, module=self.module,
            started_at=now, expires_at=now + timedelta(minutes=60),
        )
        url = reverse("bcl:submit_exam", args=[attempt.pk])
        results = self._parallel_requests([
            lambda client: client.post(url),
            lambda client: client.post(url),
        ])
        self.assertEqual([r.status_code for r in results], [302, 302])
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, CandidateAttempt.AttemptStatus.SUBMITTED)
        self.assertIsNotNone(attempt.submitted_at)
        self.assertEqual(CandidateAttempt.objects.filter(pk=attempt.pk).count(), 1)

    def test_parallel_start_repairs_duplicate_legacy_attempts(self):
        now = timezone.now()
        old = CandidateAttempt.objects.create(
            candidate=self.candidate, module=self.module,
            started_at=now - timedelta(minutes=10),
            expires_at=now + timedelta(minutes=40),
        )
        newest = CandidateAttempt.objects.create(
            candidate=self.candidate, module=self.module,
            started_at=now - timedelta(minutes=5),
            expires_at=now + timedelta(minutes=45),
        )
        url = reverse("bcl:start_exam", args=[self.module.pk])
        results = self._parallel_requests([
            lambda client: client.post(url, {"accept_rules": "yes"}),
            lambda client: client.post(url, {"accept_rules": "yes"}),
        ])
        self.assertEqual([r.status_code for r in results], [302, 302])
        old.refresh_from_db()
        newest.refresh_from_db()
        self.assertEqual(old.status, CandidateAttempt.AttemptStatus.AUTO_SUBMITTED)
        self.assertIsNotNone(old.submitted_at)
        self.assertEqual(newest.status, CandidateAttempt.AttemptStatus.IN_PROGRESS)
        self.assertEqual(CandidateAttempt.objects.filter(
            candidate=self.candidate, module=self.module,
            status=CandidateAttempt.AttemptStatus.IN_PROGRESS,
        ).count(), 1)
