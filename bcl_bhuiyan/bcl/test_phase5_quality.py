"""Phase 5 Step 2 integration, access-control and content QA regressions."""
import json
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.core.exceptions import ValidationError
from .models import IELTSMockTest, ExamModule, ExamSection, Question, QuestionOption, CandidateAttempt, CandidateAnswer
from .testbank import readiness, import_test


class CandidateWorkflowQualityTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.candidate = User.objects.create_user('qa_candidate', password='safe-test-pass')
        self.other = User.objects.create_user('qa_other', password='safe-test-pass')
        self.staff = User.objects.create_user('qa_staff', password='safe-test-pass', is_staff=True)
        self.test = IELTSMockTest.objects.create(test_number=1, title='QA practice', is_published=True)
        self.module = ExamModule.objects.create(mock_test=self.test, module_type='reading', duration_minutes=60)
        self.section = ExamSection.objects.create(module=self.module, title='Passage', passage='Practice text')
        self.question = Question.objects.create(section=self.section, order=1, question_type='mcq', question_text='Choose A', correct_answer='A')
        QuestionOption.objects.create(question=self.question, option_key='A', option_text='Correct', is_correct=True, order=1)
        QuestionOption.objects.create(question=self.question, option_key='B', option_text='Incorrect', order=2)

    def start(self):
        self.client.force_login(self.candidate)
        response = self.client.post(reverse('bcl:start_exam', args=[self.module.pk]), {'accept_rules':'yes'})
        self.assertEqual(response.status_code, 302)
        return CandidateAttempt.objects.get(candidate=self.candidate, module=self.module)

    def save(self, attempt, question=None, answer='A', flagged=True):
        return self.client.post(reverse('bcl:save_exam_answer', args=[attempt.pk]), data=json.dumps({'question_id': (question or self.question).pk, 'answer_text':answer, 'is_flagged':flagged}), content_type='application/json')

    def test_candidate_start_save_submit_score_and_lock(self):
        attempt = self.start()
        self.assertEqual(self.save(attempt).status_code, 200)
        self.assertTrue(CandidateAnswer.objects.get(attempt=attempt).is_flagged)
        self.assertEqual(self.client.post(reverse('bcl:submit_exam', args=[attempt.pk])).status_code, 302)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, 'submitted')
        self.assertEqual(attempt.raw_score, 1)
        self.assertIsNone(attempt.band_score)  # only complete 40-question modules
        self.assertEqual(self.save(attempt).status_code, 409)
        self.assertEqual(CandidateAnswer.objects.get(attempt=attempt).awarded_marks, 1)

    def test_repeated_start_reuses_active_attempt(self):
        first = self.start()
        second = self.start()
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(CandidateAttempt.objects.filter(candidate=self.candidate).count(), 1)

    def test_cross_candidate_access_denied(self):
        attempt = self.start()
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse('bcl:exam_timer', args=[attempt.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('bcl:exam_result', args=[attempt.pk])).status_code, 404)
        self.assertEqual(self.save(attempt).status_code, 404)

    def test_cross_module_question_denied(self):
        attempt = self.start()
        other_module = ExamModule.objects.create(mock_test=self.test, module_type='listening')
        section = ExamSection.objects.create(module=other_module, title='Audio')
        foreign = Question.objects.create(section=section, question_type='short_answer', question_text='Other', correct_answer='X')
        self.assertEqual(self.save(attempt, question=foreign).status_code, 404)
        self.assertFalse(CandidateAnswer.objects.filter(attempt=attempt).exists())

    def test_invalid_payloads_rejected(self):
        attempt = self.start()
        url = reverse('bcl:save_exam_answer', args=[attempt.pk])
        self.assertEqual(self.client.post(url, data='{', content_type='application/json').status_code, 400)
        self.assertEqual(self.save(attempt, answer='Z').status_code, 400)
        self.assertEqual(self.save(attempt, answer='X'*20001).status_code, 400)
        self.assertFalse(CandidateAnswer.objects.filter(attempt=attempt).exists())

    def test_second_focus_violation_auto_submits(self):
        attempt = self.start()
        url = reverse('bcl:report_exam_violation', args=[attempt.pk])
        for expected in (1, 2):
            response = self.client.post(url, data=json.dumps({'reason':'tab_hidden'}), content_type='application/json')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['violation_count'], expected)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, 'auto_submitted')
        self.assertEqual(self.save(attempt).status_code, 409)

    def test_expired_attempt_cannot_save(self):
        attempt = self.start()
        CandidateAttempt.objects.filter(pk=attempt.pk).update(expires_at=timezone.now()-timedelta(seconds=1))
        self.assertEqual(self.save(attempt).status_code, 409)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, 'auto_submitted')

    def test_staff_cannot_take_candidate_exam(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.post(reverse('bcl:start_exam', args=[self.module.pk]), {'accept_rules':'yes'}).status_code, 302)
        self.assertFalse(CandidateAttempt.objects.filter(candidate=self.staff).exists())

    def test_unpublished_test_cannot_start(self):
        self.test.is_published = False
        self.test.save(update_fields=['is_published'])
        self.client.force_login(self.candidate)
        self.assertEqual(self.client.post(reverse('bcl:start_exam', args=[self.module.pk]), {'accept_rules':'yes'}).status_code, 404)


class TestBankQualityTests(TestCase):
    def test_unconfigured_slot_fails_readiness(self):
        test = IELTSMockTest.objects.create(test_number=3, title='Empty slot')
        self.assertEqual(len(readiness(test)), 3)

    def test_atomic_rollback_on_invalid_question(self):
        payload = {'test_number':4, 'title':'Invalid', 'modules':[{'module_type':'reading','sections':[{'questions':[{'question_type':'invalid'}]}]}]}
        with self.assertRaises(ValidationError):
            import_test(payload)
        self.assertFalse(IELTSMockTest.objects.filter(test_number=4).exists())

    def test_duplicate_import_does_not_mutate_existing(self):
        existing = IELTSMockTest.objects.create(test_number=5, title='Keep original')
        original_module = ExamModule.objects.create(
            mock_test=existing, module_type='reading', duration_minutes=60
        )
        with self.assertRaises(ValidationError):
            import_test({'test_number': 5, 'title': 'Replace', 'modules': []})
        existing.refresh_from_db()
        self.assertEqual(existing.title, 'Keep original')
        self.assertTrue(ExamModule.objects.filter(pk=original_module.pk, mock_test=existing).exists())
