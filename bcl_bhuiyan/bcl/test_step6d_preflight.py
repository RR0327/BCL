"""Step 6D structural preflight and nonmutation tests."""
import json
import tempfile
from io import StringIO
from pathlib import Path
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from bcl.models import IELTSMockTest
from bcl.management.commands.preflight_testbank import validate_payload


def complete_payload():
    modules = []
    for kind, section_count, question_count in [('reading', 3, 40), ('listening', 4, 40), ('writing', 2, 2)]:
        sections = []
        for i in range(section_count):
            # Allocate the remainder to earlier sections (Reading: 14, 13, 13).
            # Integer division alone silently drops one of the 40 questions.
            n = question_count // section_count + (1 if i < question_count % section_count else 0)
            questions = []
            for j in range(n):
                if kind == 'writing':
                    questions.append({'question_type': 'essay', 'question_text': 'Write an essay about urban transport.'})
                else:
                    questions.append({'question_type': 'mcq', 'question_text': 'Which option best fits the text?', 'correct_answer': 'A', 'options': [{'option_key': 'A', 'option_text': 'Correct', 'is_correct': True}, {'option_key': 'B', 'option_text': 'Incorrect', 'is_correct': False}]})
            sections.append({'title': f'Section {i+1}', 'passage': 'An original substantial reading passage about city planning.' if kind == 'reading' else '', 'questions': questions})
        modules.append({'module_type': kind, 'sections': sections})
    return {'test_number': 1, 'title': 'Practice test', 'modules': modules}


class Step6DPreflightTests(TestCase):
    def test_question_distribution_preserves_required_totals(self):
        payload = complete_payload()
        expected = {'reading': [14, 13, 13], 'listening': [10, 10, 10, 10], 'writing': [1, 1]}
        for module in payload['modules']:
            actual = [len(section['questions']) for section in module['sections']]
            self.assertEqual(actual, expected[module['module_type']])
            self.assertEqual(sum(actual), {'reading': 40, 'listening': 40, 'writing': 2}[module['module_type']])

    def test_complete_structure_has_only_audio_manual_checks(self):
        issues = validate_payload(complete_payload())
        self.assertEqual(issues, [])

    def test_incomplete_payload_rejected(self):
        issues = validate_payload({'test_number': 1, 'title': 'T', 'modules': []})
        self.assertTrue(any('reading: module missing' in issue for issue in issues))

    def test_placeholder_rejected(self):
        data = complete_payload()
        data['modules'][0]['sections'][0]['passage'] = 'Insert passage here'
        self.assertTrue(any('original passage required' in x for x in validate_payload(data)))

    def test_duplicate_options_rejected(self):
        data = complete_payload()
        data['modules'][0]['sections'][0]['questions'][0]['options'][1]['option_key'] = 'A'
        self.assertTrue(any('option keys' in x for x in validate_payload(data)))

    def test_invalid_writing_question_rejected(self):
        data = complete_payload()
        data['modules'][2]['sections'][0]['questions'][0]['question_type'] = 'mcq'
        self.assertTrue(any('writing requires essay' in x for x in validate_payload(data)))

    def test_command_failure_does_not_modify_database(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'payload.json'
            p.write_text(json.dumps({'test_number': 1, 'title': 'T', 'modules': []}))
            with self.assertRaises(CommandError):
                call_command('preflight_testbank', '--file', str(p), stdout=StringIO())
        self.assertEqual(IELTSMockTest.objects.count(), 0)

    def test_command_report_export_without_database_write(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'payload.json'
            out = Path(d) / 'report.json'
            p.write_text(json.dumps({'test_number': 1, 'title': 'T', 'modules': []}))
            with self.assertRaises(CommandError):
                call_command('preflight_testbank', '--file', str(p), '--output', str(out), stdout=StringIO())
            self.assertFalse(json.loads(out.read_text())['structural_preflight_pass'])
        self.assertEqual(IELTSMockTest.objects.count(), 0)
