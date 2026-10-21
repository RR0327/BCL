"""Step 6C read-only staging audit regression tests."""
import json
import tempfile
from io import StringIO
from pathlib import Path
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from bcl.models import IELTSMockTest


class StagingAuditTests(TestCase):
    def run_audit(self, *args, **kwargs):
        stream = StringIO()
        call_command('audit_staging', *args, stdout=stream, **kwargs)
        return json.loads(stream.getvalue())

    def test_empty_database_reports_missing_slots(self):
        report = self.run_audit()
        self.assertEqual(report['counts']['mock_tests'], 0)
        self.assertEqual(len(report['missing_test_slots']), 30)
        self.assertEqual(report['ready_tests'], 0)

    def test_initialized_slots_have_no_missing_numbers(self):
        call_command('manage_testbank', '--initialize', stdout=StringIO())
        report = self.run_audit()
        self.assertEqual(report['counts']['mock_tests'], 30)
        self.assertEqual(report['missing_test_slots'], [])
        self.assertEqual(report['ready_tests'], 0)

    def test_incomplete_published_test_is_flagged(self):
        IELTSMockTest.objects.create(test_number=1, title='Incomplete', is_published=True)
        report = self.run_audit()
        self.assertEqual(report['published_tests'], 1)
        self.assertEqual(report['published_test_readiness_issues'][0]['test_number'], 1)
        self.assertTrue(report['published_test_readiness_issues'][0]['problems'])

    def test_strict_rejects_missing_slots(self):
        with self.assertRaises(CommandError):
            self.run_audit('--strict')

    def test_strict_accepts_empty_unpublished_slots(self):
        call_command('manage_testbank', '--initialize', stdout=StringIO())
        report = self.run_audit('--strict')
        self.assertEqual(report['published_test_readiness_issues'], [])

    def test_report_file_contains_only_aggregate_data(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'audit.json'
            report = self.run_audit('--output', str(path))
            self.assertEqual(json.loads(path.read_text(encoding='utf-8')), report)
            self.assertNotIn('username', path.read_text(encoding='utf-8'))

    def test_require_postgres_rejects_non_postgres(self):
        from django.db import connection
        if connection.vendor != 'postgresql':
            with self.assertRaises(CommandError):
                self.run_audit('--require-postgres')
