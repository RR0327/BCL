"""Step 6L: cross-endpoint concurrency regression tests on real PostgreSQL.

These tests run in separate transactions and use the public candidate routes.
They deliberately avoid depending on which concurrent request acquires the
candidate lock first: both valid serial outcomes are accepted.
"""
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection, connections
from django.test import Client, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from bcl.models import CandidateAnswer, CandidateAttempt, ExamModule, ExamSection, IELTSMockTest, Question


class PostgreSQLCrossEndpointRaceTests(TransactionTestCase):
    databases = {"default"}

    def tearDown(self):
        super().tearDown()
        connections.close_all()

    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL is required for row-lock concurrency tests")
        self.user = get_user_model().objects.create_user(
            username="step6l_candidate", password="test-only-password"
        )
        mock = IELTSMockTest.objects.create(test_number=28, title="Step 6L", is_published=True)
        self.module = ExamModule.objects.create(
            mock_test=mock, module_type="reading", duration_minutes=60
        )
        section = ExamSection.objects.create(
            module=self.module, title="Section", passage="Original test passage"
        )
        self.question = Question.objects.create(
            section=section, order=1, question_type="short_answer",
            question_text="What is the sample word?", correct_answer="sample"
        )
        now = timezone.now()
        self.attempt = CandidateAttempt.objects.create(
            candidate=self.user, module=self.module,
            started_at=now, expires_at=now + timedelta(minutes=60),
        )

    def parallel(self, actions):
        barrier = Barrier(len(actions))

        def worker(action):
            close_old_connections()
            try:
                client = Client()
                client.force_login(self.user)
                barrier.wait(timeout=20)
                return action(client)
            finally:
                close_old_connections()
                connections.close_all()

        with ThreadPoolExecutor(max_workers=len(actions)) as pool:
            futures = [pool.submit(worker, action) for action in actions]
            return [future.result(timeout=40) for future in futures]

    def answer(self, client):
        return client.post(
            reverse("bcl:save_exam_answer", args=[self.attempt.pk]),
            data=json.dumps({
                "question_id": self.question.pk,
                "answer_text": "sample",
                "is_flagged": False,
            }),
            content_type="application/json",
        )

    def test_answer_and_submission_serialize_without_post_close_write(self):
        responses = self.parallel([
            self.answer,
            lambda client: client.post(reverse("bcl:submit_exam", args=[self.attempt.pk])),
        ])
        self.assertIn(responses[0].status_code, (200, 409))
        self.assertEqual(responses[1].status_code, 302)
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, CandidateAttempt.AttemptStatus.SUBMITTED)
        answers = CandidateAnswer.objects.filter(attempt=self.attempt, question=self.question)
        if responses[0].status_code == 200:
            self.assertEqual(answers.count(), 1)
            self.assertEqual(answers.get().answer_text, "sample")
        else:
            self.assertEqual(answers.count(), 0)

    def test_two_parallel_answer_writes_have_single_answer_row(self):
        responses = self.parallel([self.answer, self.answer])
        self.assertEqual([r.status_code for r in responses], [200, 200])
        answers = CandidateAnswer.objects.filter(attempt=self.attempt, question=self.question)
        self.assertEqual(answers.count(), 1)
        self.assertEqual(answers.get().answer_text, "sample")

    def test_violation_and_submission_cannot_leave_active_attempt(self):
        violation_url = reverse("bcl:report_exam_violation", args=[self.attempt.pk])
        responses = self.parallel([
            lambda client: client.post(
                violation_url,
                data=json.dumps({"reason": "window_blur"}),
                content_type="application/json",
            ),
            lambda client: client.post(reverse("bcl:submit_exam", args=[self.attempt.pk])),
        ])
        self.assertIn(responses[0].status_code, (200, 409))
        self.assertEqual(responses[1].status_code, 302)
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, CandidateAttempt.AttemptStatus.SUBMITTED)
        self.assertIn(self.attempt.violation_count, (0, 1))
        self.assertIsNotNone(self.attempt.submitted_at)

    def test_expired_timer_and_submission_finalize_once(self):
        self.attempt.expires_at = timezone.now() - timedelta(seconds=1)
        self.attempt.save(update_fields=["expires_at"])
        responses = self.parallel([
            lambda client: client.get(reverse("bcl:exam_timer", args=[self.attempt.pk])),
            lambda client: client.post(reverse("bcl:submit_exam", args=[self.attempt.pk])),
        ])
        self.assertEqual(responses[0].status_code, 200)
        self.assertEqual(responses[1].status_code, 302)
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, CandidateAttempt.AttemptStatus.AUTO_SUBMITTED)
        self.assertIsNotNone(self.attempt.submitted_at)
        self.assertEqual(responses[0].json()["remaining_seconds"], 0)
