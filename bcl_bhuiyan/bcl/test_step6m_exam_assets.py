"""Step 6M: asset integrity audit regression coverage."""
import json
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from .models import IELTSMockTest, ExamModule, ExamSection, Question, QuestionOption


class ExamAssetAuditTests(TestCase):
    def setUp(self):
        self.test = IELTSMockTest.objects.create(test_number=1, title='Sample', is_published=True)
        self.module = ExamModule.objects.create(mock_test=self.test, module_type='reading')
        self.section = ExamSection.objects.create(module=self.module, order=1, title='Section', passage='Original passage')

    def report(self, **kwargs):
        out = StringIO()
        call_command('audit_exam_assets', stdout=out, **kwargs)
        return json.loads(out.getvalue())

    def test_published_incomplete_test_is_reported(self):
        report = self.report()
        self.assertEqual(report['published_tests_checked'], 1)
        self.assertEqual(report['published_tests_with_issues'], 1)
        self.assertTrue(report['findings'][0]['issues'])

    def test_unpublished_test_not_included(self):
        self.test.is_published = False
        self.test.save(update_fields=['is_published'])
        self.assertEqual(self.report()['published_tests_checked'], 0)

    def test_strict_mode_fails_for_published_incomplete_test(self):
        with self.assertRaises(CommandError):
            self.report(strict=True)

    def test_report_file_written_before_strict_failure(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'audit.json'
            with self.assertRaises(CommandError):
                self.report(strict=True, output=str(path))
            self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['published_tests_with_issues'], 1)

    def test_invalid_mcq_key_detected_without_exposing_answer(self):
        question = Question.objects.create(section=self.section, order=1, question_type='mcq', question_text='Prompt', correct_answer='SECRET', marks=1)
        QuestionOption.objects.create(question=question, order=1, option_key='A', is_correct=True)
        QuestionOption.objects.create(question=question, order=2, option_key='B', is_correct=False)
        out = StringIO()
        call_command('audit_exam_assets', stdout=out)
        self.assertIn('canonical key not among options', out.getvalue())
        self.assertNotIn('SECRET', out.getvalue())

    def test_missing_media_reference_detected_when_opted_in(self):
        self.section.audio_file.name = 'ielts/audio/missing-file.mp3'
        self.section.save(update_fields=['audio_file'])
        with patch.object(self.section.audio_file.storage, 'exists', return_value=False):
            report = self.report(verify_storage=True)
        self.assertTrue(any('audio_file object missing' in issue for issue in report['findings'][0]['issues']))

    def test_storage_not_checked_by_default(self):
        self.section.audio_file.name = 'ielts/audio/example.mp3'
        self.section.save(update_fields=['audio_file'])
        with patch.object(self.section.audio_file.storage, 'exists', side_effect=AssertionError('Unexpected storage access')):
            report = self.report()
        self.assertFalse(report['storage_existence_verified'])

    def test_storage_backend_failure_is_reported_without_exposing_path(self):
        self.section.audio_file.name = 'ielts/audio/private-file.mp3'
        self.section.save(update_fields=['audio_file'])
        with patch.object(self.section.audio_file.storage, 'exists', side_effect=OSError('private storage detail')):
            report = self.report(verify_storage=True)
        self.assertTrue(any('storage check failed' in issue for issue in report['findings'][0]['issues']))
        self.assertNotIn('private-file.mp3', json.dumps(report))
        self.assertNotIn('private storage detail', json.dumps(report))

    def test_requires_postgresql_when_requested(self):
        from django.db import connection
        if connection.vendor == 'postgresql':
            self.assertEqual(self.report(require_postgres=True)['database_vendor'], 'postgresql')
        else:
            with self.assertRaises(CommandError):
                self.report(require_postgres=True)
