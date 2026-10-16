import json
import tempfile
from pathlib import Path
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from bcl.models import IELTSMockTest
from bcl.testbank import import_test, readiness

class TestBankTests(TestCase):
    def test_initialize_creates_thirty_unpublished_slots(self):
        call_command('manage_testbank', '--initialize', verbosity=0)
        self.assertEqual(IELTSMockTest.objects.count(), 30)
        self.assertFalse(IELTSMockTest.objects.filter(is_published=True).exists())

    def test_initialize_idempotent(self):
        call_command('manage_testbank', '--initialize', verbosity=0)
        call_command('manage_testbank', '--initialize', verbosity=0)
        self.assertEqual(IELTSMockTest.objects.count(), 30)

    def test_dry_run_rolls_back(self):
        call_command('manage_testbank', '--initialize', '--dry-run', verbosity=0)
        self.assertEqual(IELTSMockTest.objects.count(), 0)

    def test_missing_modules_not_ready(self):
        test = IELTSMockTest.objects.create(test_number=1, title='Empty')
        self.assertTrue(any('module missing' in x for x in readiness(test)))

    def test_minimal_import_is_unpublished(self):
        test = import_test({'test_number': 1, 'title': 'Sample', 'modules': []})
        self.assertFalse(test.is_published)

    def test_duplicate_import_rejected(self):
        payload = {'test_number': 1, 'title': 'Sample', 'modules': []}
        import_test(payload)
        with self.assertRaises(ValidationError):
            import_test(payload)

    def test_failed_publish_rolls_back(self):
        with self.assertRaises(ValidationError):
            import_test({'test_number': 1, 'title': 'Incomplete', 'modules': []}, publish=True)
        self.assertEqual(IELTSMockTest.objects.count(), 0)

    def test_import_command(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'test.json'
            path.write_text(json.dumps({'test_number': 2, 'title': 'Imported', 'modules': []}))
            call_command('manage_testbank', '--import-json', str(path))
        self.assertTrue(IELTSMockTest.objects.filter(test_number=2, is_published=False).exists())

    def test_unsupported_question_rolls_back(self):
        payload = {'test_number': 1, 'title': 'Bad', 'modules': [{'module_type': 'reading', 'sections': [{'questions': [{'question_type': 'invalid'}]}]}]}
        with self.assertRaises(ValidationError):
            import_test(payload)
        self.assertFalse(IELTSMockTest.objects.exists())
