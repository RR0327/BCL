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


    def test_legacy_results_modal_is_completely_suppressed_in_rendered_html(self):
        target = self.make_attempt(self.listening)
        response = self.client.get(reverse('bcl:mock_listening', args=[self.mock.pk]))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8', errors='replace')
        self.assertIn('#result-modal', content)
        self.assertIn('hideAllLegacyModals', content)
        self.assertIn('div[id*="result-modal"]', content)

    def test_listening_submission_persists_raw_score_band_and_answers_payload(self):
        import json
        from decimal import Decimal
        from .scoring import finalize_attempt_score
        from .result_exports import get_module_attempt_data

        target = self.make_attempt(self.listening)
        answers_dict = {
            str(i): {
                "user_answer": f"cand_answer_{i}" if i != 1 else "Anthony",
                "correct_answer": f"correct_answer_{i}" if i != 1 else "Anthony",
                "is_correct": (i == 1 or i <= 20)
            }
            for i in range(1, 41)
        }
        raw_score = sum(1 for v in answers_dict.values() if v["is_correct"]) # 20
        payload_data = {
            "score": raw_score,
            "total": 40,
            "band_score": "5.5",
            "answers": answers_dict
        }

        submit_url = reverse('bcl:mock_listening_submit', args=[self.mock.pk])
        resp = self.client.post(
            submit_url,
            data={
                "attempt_id": str(target.pk),
                "raw_score": raw_score,
                "band_score": "5.5",
                "module_type": "listening",
                "answers_payload": json.dumps(payload_data)
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("status"), "ok")

        target.refresh_from_db()
        self.assertEqual(target.raw_score, 20)
        self.assertEqual(target.band_score, Decimal("5.5"))
        self.assertEqual(target.status, CandidateAttempt.AttemptStatus.SUBMITTED)
        self.assertIsNotNone(target.answers_payload)
        self.assertEqual(target.answers_payload["score"], 20)
        self.assertEqual(target.answers_payload["answers"]["1"]["user_answer"], "Anthony")
        self.assertEqual(target.answers_payload["answers"]["1"]["correct_answer"], "Anthony")

        # Test idempotence: finalize_attempt_score should NEVER zero out the listening score
        finalize_attempt_score(target)
        target.refresh_from_db()
        self.assertEqual(target.raw_score, 20)
        self.assertEqual(target.band_score, Decimal("5.5"))

        # Test result exports extracts 40 questions with answers
        export_data = get_module_attempt_data(target.pk)
        self.assertEqual(len(export_data["questions_data"]), 40)
        self.assertEqual(export_data["questions_data"][0]["candidate_answer"], "Anthony")
        self.assertTrue(export_data["questions_data"][0]["is_correct"])

    def test_listening_html_contains_back_and_dashboard_exit_warning(self):
        target = self.make_attempt(self.listening)
        response = self.client.get(reverse('bcl:mock_listening', args=[self.mock.pk]))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode('utf-8', errors='replace')
        self.assertIn('id="bclHeaderBackBtn"', html)
        self.assertIn('handleExitPrompt', html)
        self.assertIn('rearmHistoryTrap', html)
        self.assertIn('const isFullMock = false;', html)
        self.assertIn('Going back will submit your examination', html)
        self.assertIn('bclConfirmAndSubmit', html)
        self.assertIn('id="bcl-violation-modal"', html)
        self.assertIn(':not(#bcl-violation-modal)', html)

    def test_listening_full_mock_html_sets_is_full_mock_true(self):
        full = FullMockAttempt.objects.create(
            candidate=self.user, mock_test=self.mock,
            status=FullMockAttempt.AttemptStatus.IN_PROGRESS,
            current_step='listening', started_at=timezone.now()
        )
        target = self.make_attempt(self.listening, full)
        full.listening_attempt = target
        full.save(update_fields=['listening_attempt'])
        response = self.client.get(reverse('bcl:mock_listening', args=[self.mock.pk]))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode('utf-8', errors='replace')
        self.assertIn('const isFullMock = true;', html)
        self.assertIn('Going back will exit your All-Module exam', html)

    def test_exit_full_mock_via_ajax_returns_json_and_completes_exam(self):
        full = FullMockAttempt.objects.create(
            candidate=self.user, mock_test=self.mock,
            status=FullMockAttempt.AttemptStatus.IN_PROGRESS,
            current_step='listening', started_at=timezone.now()
        )
        target = self.make_attempt(self.listening, full)
        full.listening_attempt = target
        full.save(update_fields=['listening_attempt'])

        resp = self.client.post(
            reverse('bcl:mock_listening_submit', args=[self.mock.pk]),
            data={
                'attempt_id': str(target.pk),
                'raw_score': '25',
                'band_score': '6.0',
                'exit_full_mock': 'true',
                'module_type': 'listening'
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get('status'), 'ok')
        self.assertIn('full-mock', data.get('next_url'))

        target.refresh_from_db()
        full.refresh_from_db()
        self.assertEqual(target.status, CandidateAttempt.AttemptStatus.SUBMITTED)
        self.assertEqual(full.status, FullMockAttempt.AttemptStatus.SUBMITTED)
        self.assertEqual(full.current_step, 'completed')

    def test_two_integrity_warnings_and_auto_submission_on_third_violation(self):
        import json
        target = self.make_attempt(self.listening)
        violation_url = reverse('bcl:report_exam_violation', args=[target.pk])

        # Violation 1
        r1 = self.client.post(
            violation_url,
            data=json.dumps({'reason': 'tab_hidden'}),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(r1.status_code, 200)
        d1 = r1.json()
        self.assertEqual(d1['violation_count'], 1)
        self.assertTrue(d1['warning'])
        self.assertFalse(d1['auto_submitted'])
        self.assertIn('1 of 2', d1['warning_title'])

        # Violation 2
        r2 = self.client.post(
            violation_url,
            data=json.dumps({'reason': 'window_blur'}),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(r2.status_code, 200)
        d2 = r2.json()
        self.assertEqual(d2['violation_count'], 2)
        self.assertTrue(d2['warning'])
        self.assertFalse(d2['auto_submitted'])
        self.assertIn('2 of 2', d2['warning_title'])

        # Violation 3 -> Auto-Submit
        r3 = self.client.post(
            violation_url,
            data=json.dumps({
                'reason': 'tab_hidden',
                'raw_score': '18',
                'answers_payload': {'score': 18, 'total': 40, 'answers': {}}
            }),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(r3.status_code, 200)
        d3 = r3.json()
        self.assertEqual(d3['violation_count'], 3)
        self.assertFalse(d3['warning'])
        self.assertTrue(d3['auto_submitted'])
        self.assertIsNotNone(d3.get('redirect_url'))

        target.refresh_from_db()
        self.assertEqual(target.status, CandidateAttempt.AttemptStatus.AUTO_SUBMITTED)
        self.assertEqual(target.raw_score, 18)
        self.assertEqual(target.violation_count, 3)

    def test_listening_exam_result_renders_post_submission_interface_for_single_mock(self):
        target = self.make_attempt(self.listening)
        target.status = CandidateAttempt.AttemptStatus.SUBMITTED
        target.raw_score = 28
        target.band_score = "6.5"
        target.answers_payload = {
            "score": 28,
            "total": 40,
            "answers": {
                "1": {"user_answer": "Anthony", "correct_answer": "Anthony", "is_correct": True},
                "2": {"user_answer": "wrong text", "correct_answer": "1st June", "is_correct": False}
            }
        }
        target.save()

        resp = self.client.get(reverse('bcl:exam_result', args=[target.pk]))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode('utf-8')
        self.assertIn('Exam Result &amp; Answers Review', html)
        self.assertIn('bcl-modal-score-banner', html)
        self.assertIn('28 / 40', html)
        self.assertIn('Band 6.5', html)
        self.assertIn('Saved to Database', html)
        self.assertIn('class="bcl-review-row"', html)
        self.assertEqual(html.count('class="bcl-review-row"'), 40)
        self.assertIn('Return to Dashboard', html)

    def test_listening_exam_result_renders_post_submission_interface_for_full_mock(self):
        full = FullMockAttempt.objects.create(
            candidate=self.user, mock_test=self.mock,
            status=FullMockAttempt.AttemptStatus.SUBMITTED,
            current_step='completed', started_at=timezone.now()
        )
        target = self.make_attempt(self.listening, full)
        target.status = CandidateAttempt.AttemptStatus.SUBMITTED
        target.raw_score = 32
        target.band_score = "7.5"
        target.save()
        full.listening_attempt = target
        full.save(update_fields=['listening_attempt'])

        resp = self.client.get(reverse('bcl:exam_result', args=[target.pk]))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode('utf-8')
        self.assertIn('Exam Result &amp; Answers Review', html)
        self.assertIn('32 / 40', html)
        self.assertIn('Return to All Modules Result', html)

    def test_full_mock_result_page_contains_listening_modal_interface(self):
        full = FullMockAttempt.objects.create(
            candidate=self.user, mock_test=self.mock,
            status=FullMockAttempt.AttemptStatus.SUBMITTED,
            current_step='completed', started_at=timezone.now()
        )
        target = self.make_attempt(self.listening, full)
        target.status = CandidateAttempt.AttemptStatus.SUBMITTED
        target.raw_score = 30
        target.band_score = "7.0"
        target.save()
        full.listening_attempt = target
        full.save(update_fields=['listening_attempt'])

        resp = self.client.get(reverse('bcl:full_mock_result', args=[full.pk]))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode('utf-8')
        self.assertIn('View Listening Question Review', html)
        self.assertIn('openBclListeningModal', html)
        self.assertIn('id="bcl-listening-modal"', html)
        self.assertIn('Exam Result &amp; Answers Review', html)
        self.assertIn('30 / 40', html)
