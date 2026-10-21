"""Step 6G: candidate-session hardening regressions."""
import json
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from bcl.models import (IELTSMockTest, ExamModule, ExamSection, Question,
                        QuestionOption, CandidateAttempt, CandidateAnswer)
from bcl.management.commands.audit_candidate_workflows import audit_candidate_workflows


class CandidateSessionHardeningTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='step6g_candidate', password='test-pass')
        self.other = get_user_model().objects.create_user(username='step6g_other', password='test-pass')
        self.mock = IELTSMockTest.objects.create(test_number=28, title='6G', is_published=True)
        self.module = ExamModule.objects.create(mock_test=self.mock, module_type='reading', duration_minutes=60)
        section = ExamSection.objects.create(module=self.module, title='Reading', passage='Passage')
        self.question = Question.objects.create(section=section, order=1, question_type='mcq', question_text='Choose', correct_answer='A')
        QuestionOption.objects.create(question=self.question, option_key='A', option_text='Yes', order=1, is_correct=True)
        QuestionOption.objects.create(question=self.question, option_key='B', option_text='No', order=2)
        self.client.force_login(self.user)

    def start(self):
        return self.client.post(reverse('bcl:start_exam', args=[self.module.pk]), {'accept_rules':'yes'})

    def test_repeated_start_reuses_one_live_attempt(self):
        self.assertEqual(self.start().status_code, 302)
        first = CandidateAttempt.objects.get(candidate=self.user)
        self.assertEqual(self.start().status_code, 302)
        self.assertEqual(CandidateAttempt.objects.filter(candidate=self.user).count(), 1)
        self.assertEqual(CandidateAttempt.objects.get(candidate=self.user).pk, first.pk)

    def test_duplicate_live_sessions_closed_on_start(self):
        now = timezone.now()
        old = CandidateAttempt.objects.create(candidate=self.user, module=self.module,
            started_at=now-timedelta(minutes=2), expires_at=now+timedelta(minutes=58))
        latest = CandidateAttempt.objects.create(candidate=self.user, module=self.module,
            started_at=now-timedelta(minutes=1), expires_at=now+timedelta(minutes=59))
        self.assertEqual(audit_candidate_workflows()['anomalies']['duplicate_active_attempt_groups'], 1)
        self.assertEqual(self.start().status_code, 302)
        old.refresh_from_db(); latest.refresh_from_db()
        self.assertEqual(old.status, CandidateAttempt.AttemptStatus.AUTO_SUBMITTED)
        self.assertIsNotNone(old.submitted_at)
        self.assertEqual(latest.status, CandidateAttempt.AttemptStatus.IN_PROGRESS)
        self.assertEqual(audit_candidate_workflows()['anomalies']['duplicate_active_attempt_groups'], 0)

    def test_expired_session_closed_before_new_start(self):
        now = timezone.now()
        expired = CandidateAttempt.objects.create(candidate=self.user, module=self.module,
            started_at=now-timedelta(minutes=61), expires_at=now-timedelta(minutes=1))
        self.assertEqual(self.start().status_code, 302)
        expired.refresh_from_db()
        self.assertEqual(expired.status, CandidateAttempt.AttemptStatus.AUTO_SUBMITTED)
        self.assertEqual(CandidateAttempt.objects.filter(candidate=self.user, module=self.module,
            status=CandidateAttempt.AttemptStatus.IN_PROGRESS).count(), 1)

    def test_closed_duplicate_rejects_answer_saves(self):
        now = timezone.now()
        old = CandidateAttempt.objects.create(candidate=self.user, module=self.module,
            started_at=now-timedelta(minutes=2), expires_at=now+timedelta(minutes=58))
        CandidateAttempt.objects.create(candidate=self.user, module=self.module,
            started_at=now-timedelta(minutes=1), expires_at=now+timedelta(minutes=59))
        self.start()
        response = self.client.post(reverse('bcl:save_exam_answer', args=[old.pk]),
            data=json.dumps({'question_id':self.question.pk, 'answer_text':'A', 'is_flagged':False}),
            content_type='application/json')
        self.assertEqual(response.status_code, 409)
        self.assertFalse(CandidateAnswer.objects.filter(attempt=old).exists())

    def test_candidate_cannot_start_unpublished_exam(self):
        self.mock.is_published = False
        self.mock.save(update_fields=['is_published'])
        self.assertEqual(self.start().status_code, 404)
        self.assertFalse(CandidateAttempt.objects.exists())

    def test_other_candidate_cannot_save_answers(self):
        self.start()
        attempt = CandidateAttempt.objects.get(candidate=self.user)
        self.client.force_login(self.other)
        response = self.client.post(reverse('bcl:save_exam_answer', args=[attempt.pk]),
            data=json.dumps({'question_id':self.question.pk, 'answer_text':'A', 'is_flagged':False}),
            content_type='application/json')
        self.assertEqual(response.status_code, 404)
        self.assertFalse(CandidateAnswer.objects.exists())
