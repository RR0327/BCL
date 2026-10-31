"""Regression tests for explicit Listening completion and attempt isolation."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import CandidateAttempt, ExamModule, FullMockAttempt, IELTSMockTest


class ListeningIsolationRegressionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='listening_isolation_candidate', password='TestPassword123!'
        )
        self.client.force_login(self.user)
        self.mock = IELTSMockTest.objects.create(
            test_number=8, title='Isolation regression mock', is_published=True
        )
        self.other_mock = IELTSMockTest.objects.create(
            test_number=9, title='Unrelated mock', is_published=True
        )
        self.listening = ExamModule.objects.create(
            mock_test=self.mock, module_type=ExamModule.ModuleType.LISTENING,
            duration_minutes=40, is_active=True
        )
        self.other_listening = ExamModule.objects.create(
            mock_test=self.other_mock, module_type=ExamModule.ModuleType.LISTENING,
            duration_minutes=40, is_active=True
        )
        self.reading = ExamModule.objects.create(
            mock_test=self.mock, module_type=ExamModule.ModuleType.READING,
            duration_minutes=60, is_active=True
        )

    def make_attempt(self, module, full=None):
        now = timezone.now()
        return CandidateAttempt.objects.create(
            candidate=self.user, module=module, full_mock=full,
            status=CandidateAttempt.AttemptStatus.IN_PROGRESS,
            started_at=now, expires_at=now + timedelta(minutes=40)
        )

    def test_submission_only_changes_target_mock(self):
        target = self.make_attempt(self.listening)
        other = self.make_attempt(self.other_listening)
        response = self.client.post(
            reverse('bcl:mock_listening_submit', args=[self.mock.pk]),
            {'attempt_id': str(target.pk), 'raw_score': '20'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 200)
        target.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual(target.status, CandidateAttempt.AttemptStatus.SUBMITTED)
        self.assertEqual(other.status, CandidateAttempt.AttemptStatus.IN_PROGRESS)

    def test_mismatched_attempt_id_cannot_submit(self):
        target = self.make_attempt(self.listening)
        other = self.make_attempt(self.other_listening)
        response = self.client.post(
            reverse('bcl:mock_listening_submit', args=[self.mock.pk]),
            {'attempt_id': str(other.pk)},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 409)
        target.refresh_from_db()
        self.assertEqual(target.status, CandidateAttempt.AttemptStatus.IN_PROGRESS)

    def test_reading_url_does_not_auto_submit_listening(self):
        full = FullMockAttempt.objects.create(
            candidate=self.user, mock_test=self.mock,
            status=FullMockAttempt.AttemptStatus.IN_PROGRESS,
            current_step='listening', started_at=timezone.now()
        )
        listening_attempt = self.make_attempt(self.listening, full)
        full.listening_attempt = listening_attempt
        full.save(update_fields=['listening_attempt'])
        response = self.client.get(reverse('bcl:mock_reading', args=[self.mock.pk]))
        self.assertEqual(response.status_code, 302)
        listening_attempt.refresh_from_db()
        full.refresh_from_db()
        self.assertEqual(listening_attempt.status, CandidateAttempt.AttemptStatus.IN_PROGRESS)
        self.assertEqual(full.current_step, 'listening')

    def test_html_bridges_only_submit_on_explicit_trigger(self):
        from .exam_views import LISTENING_BRIDGE_TEMPLATE
        self.assertNotIn('window.checkAnswers =', LISTENING_BRIDGE_TEMPLATE)
        self.assertEqual(LISTENING_BRIDGE_TEMPLATE, '')
