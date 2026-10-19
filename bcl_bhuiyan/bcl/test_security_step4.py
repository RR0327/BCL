"""Step 4 regression: strict gates and destructive-action safety."""
import json
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from bcl.test_helpers import force_verified_staff

class ReleaseAcceptanceTests(TestCase):
    def test_empty_testbank_report_blocks_release(self):
        with TemporaryDirectory() as folder:
            out = str(Path(folder) / 'report.json')
            with self.assertRaises(CommandError):
                call_command('release_acceptance', output=out, strict=True, stdout=StringIO())
            report = json.loads(Path(out).read_text())
            self.assertEqual(len(report['test_bank']), 30)
            self.assertFalse(report['automated_gates_pass'])

    def test_read_only_report_does_not_create_tests(self):
        from bcl.models import IELTSMockTest
        with TemporaryDirectory() as folder:
            call_command('release_acceptance', output=str(Path(folder)/'report.json'), stdout=StringIO())
        self.assertEqual(IELTSMockTest.objects.count(), 0)

    def test_pg_rehearsal_rejects_sqlite(self):
        with self.assertRaises(CommandError):
            call_command('postgres_rehearsal', destination='unused', stdout=StringIO())

    def test_staff_mfa_required_but_verified_staff_allowed(self):
        staff = get_user_model().objects.create_user('step4_staff', password='StrongPass123!', is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.client.get('/admin/').status_code, 302)
        force_verified_staff(self.client, staff)
        self.assertNotEqual(self.client.get('/admin/').get('Location', ''), reverse('bcl:mfa_setup'))
