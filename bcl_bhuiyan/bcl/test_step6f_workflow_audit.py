"""Step 6F: read-only workflow integrity and candidate end-to-end regressions."""
import json
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from bcl.management.commands.audit_candidate_workflows import audit_candidate_workflows
from bcl.models import IELTSMockTest, ExamModule, ExamSection, Question, QuestionOption, CandidateAttempt, CandidateAnswer


class CandidateWorkflowAuditTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='step6f_candidate', password='safe-test-pass')
        self.other = get_user_model().objects.create_user(username='step6f_other', password='safe-test-pass')
        self.mock = IELTSMockTest.objects.create(test_number=29, title='6F', is_published=True)
        self.module = ExamModule.objects.create(mock_test=self.mock, module_type='reading', duration_minutes=60)
        section = ExamSection.objects.create(module=self.module, title='Section', passage='Test passage')
        self.question = Question.objects.create(section=section, order=1, question_type='mcq', question_text='Choose', correct_answer='A')
        QuestionOption.objects.create(question=self.question, option_key='A', option_text='Correct', order=1, is_correct=True)
        QuestionOption.objects.create(question=self.question, option_key='B', option_text='Wrong', order=2)

    def start(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('bcl:start_exam', args=[self.module.pk]), {'accept_rules': 'yes'})
        self.assertEqual(response.status_code, 302)
        return CandidateAttempt.objects.get(candidate=self.user, module=self.module)

    def save(self, attempt, value='A'):
        return self.client.post(reverse('bcl:save_exam_answer', args=[attempt.pk]), data=json.dumps({'question_id':self.question.pk,'answer_text':value,'is_flagged':False}), content_type='application/json')

    def test_empty_database_has_clean_audit(self):
        report = audit_candidate_workflows()
        self.assertTrue(report['passed'])
        self.assertEqual(report['totals']['attempts'], 0)

    def test_candidate_start_answer_submit_and_score(self):
        attempt = self.start()
        self.assertEqual(self.save(attempt).status_code, 200)
        self.assertEqual(self.client.post(reverse('bcl:submit_exam', args=[attempt.pk])).status_code, 302)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, CandidateAttempt.AttemptStatus.SUBMITTED)
        self.assertEqual(attempt.raw_score, 1)
        self.assertEqual(self.save(attempt).status_code, 409)
        self.assertTrue(audit_candidate_workflows()['passed'])

    def test_other_candidate_cannot_submit_or_read_timer(self):
        attempt = self.start()
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(reverse('bcl:submit_exam', args=[attempt.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('bcl:exam_timer', args=[attempt.pk])).status_code, 404)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, CandidateAttempt.AttemptStatus.IN_PROGRESS)

    def test_cross_module_answer_detected_without_modifying_data(self):
        attempt = self.start()
        second = ExamModule.objects.create(mock_test=self.mock, module_type='listening')
        section = ExamSection.objects.create(module=second, title='Other')
        foreign = Question.objects.create(section=section, question_type='short_answer', question_text='Other')
        CandidateAnswer.objects.create(attempt=attempt, question=foreign, answer_text='private')
        report = audit_candidate_workflows()
        self.assertEqual(report['anomalies']['answer_from_different_module'], 1)
        self.assertFalse(report['passed'])
        self.assertNotIn('private', json.dumps(report))

    def test_expired_in_progress_detected(self):
        attempt = self.start()
        CandidateAttempt.objects.filter(pk=attempt.pk).update(expires_at=timezone.now()-timedelta(seconds=10))
        self.assertEqual(audit_candidate_workflows()['anomalies']['expired_in_progress'], 1)

    def test_duplicate_active_attempt_group_detected(self):
        attempt = self.start()
        CandidateAttempt.objects.create(candidate=self.user, module=self.module, started_at=attempt.started_at, expires_at=attempt.expires_at)
        self.assertEqual(audit_candidate_workflows()['anomalies']['duplicate_active_attempt_groups'], 1)

    def test_command_refuses_non_postgres_when_required(self):
        from django.db import connection
        if connection.vendor != 'postgresql':
            with self.assertRaises(CommandError):
                call_command('audit_candidate_workflows', require_postgres=True)

    def test_command_fail_on_anomaly(self):
        self.start()
        CandidateAttempt.objects.filter(candidate=self.user).update(expires_at=timezone.now()-timedelta(seconds=10))
        with self.assertRaises(CommandError):
            call_command('audit_candidate_workflows', fail_on_anomaly=True)
