"""Step 6H: legacy duplicate sessions cannot mutate candidate state."""
import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from bcl.models import (CandidateAnswer, CandidateAttempt, ExamModule,
                        ExamSection, IELTSMockTest, Question, QuestionOption)


class SupersededSessionTests(TestCase):
    def setUp(self):
        self.candidate = get_user_model().objects.create_user(username='step6h_candidate', password='pass')
        self.mock = IELTSMockTest.objects.create(test_number=29, title='6H', is_published=True)
        self.module = ExamModule.objects.create(mock_test=self.mock, module_type='reading', duration_minutes=60)
        section = ExamSection.objects.create(module=self.module, title='Reading', passage='Passage')
        self.question = Question.objects.create(section=section, order=1, question_type='mcq', question_text='Choose', correct_answer='A')
        QuestionOption.objects.create(question=self.question, option_key='A', option_text='Correct', order=1, is_correct=True)
        QuestionOption.objects.create(question=self.question, option_key='B', option_text='Incorrect', order=2)
        self.client.force_login(self.candidate)
        now = timezone.now()
        self.old = CandidateAttempt.objects.create(candidate=self.candidate, module=self.module,
            started_at=now-timedelta(minutes=2), expires_at=now+timedelta(minutes=58))
        self.new = CandidateAttempt.objects.create(candidate=self.candidate, module=self.module,
            started_at=now-timedelta(minutes=1), expires_at=now+timedelta(minutes=59))

    def save(self, attempt):
        return self.client.post(reverse('bcl:save_exam_answer', args=[attempt.pk]),
            data=json.dumps({'question_id':self.question.pk, 'answer_text':'A', 'is_flagged':False}),
            content_type='application/json')

    def test_old_session_cannot_save_answer(self):
        self.assertEqual(self.save(self.old).status_code, 409)
        self.assertFalse(CandidateAnswer.objects.filter(attempt=self.old).exists())

    def test_newest_session_can_save_answer(self):
        self.assertEqual(self.save(self.new).status_code, 200)
        self.assertEqual(CandidateAnswer.objects.filter(attempt=self.new).count(), 1)

    def test_old_session_cannot_submit(self):
        response = self.client.post(reverse('bcl:submit_exam', args=[self.old.pk]))
        self.assertEqual(response.status_code, 409)
        self.old.refresh_from_db()
        self.assertEqual(self.old.status, CandidateAttempt.AttemptStatus.IN_PROGRESS)

    def test_newest_session_can_submit(self):
        response = self.client.post(reverse('bcl:submit_exam', args=[self.new.pk]))
        self.assertEqual(response.status_code, 302)
        self.new.refresh_from_db()
        self.assertEqual(self.new.status, CandidateAttempt.AttemptStatus.SUBMITTED)

    def test_old_session_cannot_report_violation(self):
        response = self.client.post(reverse('bcl:report_exam_violation', args=[self.old.pk]),
            data=json.dumps({'reason':'tab_hidden'}), content_type='application/json')
        self.assertEqual(response.status_code, 409)
        self.old.refresh_from_db()
        self.assertEqual(self.old.violation_count, 0)

    def test_newest_session_can_report_violation(self):
        response = self.client.post(reverse('bcl:report_exam_violation', args=[self.new.pk]),
            data=json.dumps({'reason':'tab_hidden'}), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.new.refresh_from_db()
        self.assertEqual(self.new.violation_count, 1)
