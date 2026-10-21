"""Step 6E: safe read-only import planning and PostgreSQL gating."""
import json
import tempfile
from io import StringIO
from pathlib import Path
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.test.utils import override_settings
from bcl.models import IELTSMockTest, ExamModule
from bcl.test_step6d_preflight import complete_payload
from bcl.management.commands.plan_testbank_import import build_import_plan


class Step6EImportPlanTests(TestCase):
    def test_complete_payload_can_target_absent_slot(self):
        plan = build_import_plan(complete_payload(), None)
        self.assertTrue(plan['import_eligible'])
        self.assertEqual(plan['slot_status'], 'absent')

    def test_complete_payload_can_target_empty_slot(self):
        slot = IELTSMockTest.objects.create(test_number=1, title='Empty')
        plan = build_import_plan(complete_payload(), slot)
        self.assertTrue(plan['import_eligible'])
        self.assertEqual(plan['slot_status'], 'empty_unpublished')

    def test_published_slot_is_blocked(self):
        slot = IELTSMockTest.objects.create(test_number=1, title='Published', is_published=True)
        self.assertFalse(build_import_plan(complete_payload(), slot)['import_eligible'])

    def test_populated_slot_is_blocked(self):
        slot = IELTSMockTest.objects.create(test_number=1, title='Populated')
        ExamModule.objects.create(mock_test=slot, module_type='reading')
        self.assertFalse(build_import_plan(complete_payload(), slot)['import_eligible'])

    def test_incomplete_content_is_blocked(self):
        plan = build_import_plan({'test_number': 1, 'title': 'Sample', 'modules': []}, None)
        self.assertFalse(plan['import_eligible'])
        self.assertTrue(any('reading: module missing' in s for s in plan['issues']))

    def test_command_writes_report_without_mutation(self):
        IELTSMockTest.objects.create(test_number=1, title='Existing slot')
        with tempfile.TemporaryDirectory() as tmp:
            payload = Path(tmp) / 'test.json'
            report = Path(tmp) / 'plan.json'
            payload.write_text(json.dumps(complete_payload()), encoding='utf-8')
            call_command('plan_testbank_import', '--file', str(payload), '--output', str(report), stdout=StringIO())
            self.assertTrue(json.loads(report.read_text())['import_eligible'])
        self.assertEqual(IELTSMockTest.objects.get(test_number=1).title, 'Existing slot')
        self.assertEqual(ExamModule.objects.count(), 0)

    def test_blocked_command_reports_error_without_mutation(self):
        IELTSMockTest.objects.create(test_number=1, title='Published', is_published=True)
        with tempfile.TemporaryDirectory() as tmp:
            payload = Path(tmp) / 'test.json'
            payload.write_text(json.dumps(complete_payload()), encoding='utf-8')
            with self.assertRaises(CommandError):
                call_command('plan_testbank_import', '--file', str(payload), stdout=StringIO())
        self.assertEqual(IELTSMockTest.objects.count(), 1)
