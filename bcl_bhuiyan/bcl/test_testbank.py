import json
import tempfile
from pathlib import Path
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from bcl.models import IELTSMockTest, Question, QuestionOption
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

    def test_repeated_empty_slot_import_is_allowed(self):
        """An empty, unpublished slot is intentionally reusable for first content import."""
        payload = {'test_number': 1, 'title': 'Sample', 'modules': []}
        original = import_test(payload)
        updated = import_test({'test_number': 1, 'title': 'Updated Sample', 'modules': []})
        self.assertEqual(original.pk, updated.pk)
        self.assertEqual(IELTSMockTest.objects.count(), 1)
        self.assertEqual(updated.title, 'Updated Sample')

    def test_duplicate_populated_import_rejected(self):
        """Once a slot has exam content, imports must never overwrite it."""
        payload = {'test_number': 1, 'title': 'Sample', 'modules': [
            {'module_type': 'reading', 'sections': []},
        ]}
        import_test(payload)
        with self.assertRaises(ValidationError):
            import_test(payload)
        self.assertEqual(IELTSMockTest.objects.get(test_number=1).modules.count(), 1)

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

    def test_import_preserves_multiple_questions_and_blank_configuration(self):
        test = import_test({
            'test_number': 3,
            'title': 'Reading formats',
            'modules': [{
                'module_type': 'reading',
                'sections': [{
                    'title': 'Note completion',
                    'passage': 'A passage',
                    'questions': [
                        {
                            'question_type': 'fill_blank',
                            'question_text': 'The answer is ___ and ___.',
                            'question_instructions': 'Write ONE WORD ONLY.',
                            'answer_count': 2,
                            'correct_answer': 'one;;;two',
                        },
                        {
                            'question_type': 'matching',
                            'question_text': 'Which paragraph?',
                            'options': [{'option_key': 'A', 'option_text': 'Paragraph A', 'is_correct': True}],
                        },
                    ],
                }],
            }],
        })
        section = test.modules.get(module_type='reading').sections.get()
        questions = list(section.questions.order_by('order'))
        self.assertEqual(len(questions), 2)
        self.assertEqual(questions[0].answer_count, 2)
        self.assertEqual(questions[0].question_instructions, 'Write ONE WORD ONLY.')
        self.assertEqual(questions[1].options.get().option_key, 'A')

    def test_import_supports_multiple_ordered_reading_parts(self):
        test = import_test({
            'test_number': 4,
            'title': 'Three reading parts',
            'modules': [{
                'module_type': 'reading',
                'sections': [
                    {'title': 'Passage 1', 'passage': 'First passage', 'questions': []},
                    {'title': 'Passage 2', 'passage': 'Second passage', 'questions': []},
                    {'title': 'Passage 3', 'passage': 'Third passage', 'questions': []},
                ],
            }],
        })
        parts = list(test.modules.get(module_type='reading').sections.order_by('order'))
        self.assertEqual([part.title for part in parts], ['Passage 1', 'Passage 2', 'Passage 3'])
        self.assertEqual([part.passage for part in parts], ['First passage', 'Second passage', 'Third passage'])

    def test_import_supports_matching_information(self):
        test = import_test({
            'test_number': 5,
            'title': 'Matching information',
            'modules': [{
                'module_type': 'reading',
                'sections': [{
                    'passage': 'Passage',
                    'questions': [{
                        'question_type': 'matching_information',
                        'question_text': 'Which paragraph contains this information?',
                        'correct_answer': 'B',
                        'options': [
                            {'option_key': 'A', 'option_text': 'Paragraph A'},
                            {'option_key': 'B', 'option_text': 'Paragraph B', 'is_correct': True},
                        ],
                    }],
                }],
            }],
        })
        question = test.modules.get(module_type='reading').sections.get().questions.get()
        self.assertEqual(question.question_type, 'matching_information')
        self.assertEqual(question.options.get(is_correct=True).option_key, 'B')

    def test_import_allows_blank_option_text(self):
        test = import_test({
            'test_number': 6,
            'title': 'Blank option labels',
            'modules': [{
                'module_type': 'reading',
                'sections': [{
                    'passage': 'Passage',
                    'questions': [{
                        'question_type': 'matching',
                        'question_text': 'Select an option.',
                        'correct_answer': 'A',
                        'options': [{'option_key': 'A', 'is_correct': True}],
                    }],
                }],
            }],
        })
        option = test.modules.get(module_type='reading').sections.get().questions.get().options.get()
        self.assertEqual(option.option_text, '')


class EmptySlotImportRegressionTests(TestCase):
    """Import must work with initialized slots without overwriting candidate content."""

    def test_import_into_initialized_empty_slot(self):
        call_command('manage_testbank', '--initialize', verbosity=0)
        original = IELTSMockTest.objects.get(test_number=1)
        imported = import_test({'test_number': 1, 'title': 'Authorized Test', 'modules': []})
        self.assertEqual(imported.pk, original.pk)
        self.assertEqual(imported.title, 'Authorized Test')
        self.assertEqual(IELTSMockTest.objects.count(), 30)

    def test_reject_populated_unpublished_slot_without_changes(self):
        call_command('manage_testbank', '--initialize', verbosity=0)
        payload = {'test_number': 1, 'title': 'Original', 'modules': [
            {'module_type': 'reading', 'sections': []}]}
        import_test(payload)
        with self.assertRaises(ValidationError):
            import_test({'test_number': 1, 'title': 'Replacement', 'modules': []})
        test = IELTSMockTest.objects.get(test_number=1)
        self.assertEqual(test.title, 'Original')
        self.assertEqual(test.modules.count(), 1)

    def test_reject_published_empty_slot(self):
        IELTSMockTest.objects.create(test_number=1, title='Live', is_published=True)
        with self.assertRaises(ValidationError):
            import_test({'test_number': 1, 'title': 'Replace', 'modules': []})
        self.assertEqual(IELTSMockTest.objects.get(test_number=1).title, 'Live')

    def test_invalid_payload_rolls_back_existing_slot(self):
        IELTSMockTest.objects.create(test_number=1, title='Placeholder')
        with self.assertRaises(ValidationError):
            import_test({'test_number': 1, 'title': 'Should rollback', 'modules': [
                {'module_type': 'reading', 'sections': [
                    {'questions': [{'question_type': 'invalid'}]}]}]})
        self.assertEqual(IELTSMockTest.objects.get(test_number=1).title, 'Placeholder')
        self.assertFalse(IELTSMockTest.objects.get(test_number=1).modules.exists())

    def test_dry_run_existing_slot_rolls_back(self):
        IELTSMockTest.objects.create(test_number=1, title='Placeholder')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'test.json'
            path.write_text(json.dumps({'test_number': 1, 'title': 'Changed', 'modules': []}))
            call_command('manage_testbank', '--import-json', str(path), '--dry-run')
        self.assertEqual(IELTSMockTest.objects.get(test_number=1).title, 'Placeholder')

    def test_reject_non_object_module(self):
        with self.assertRaises(ValidationError):
            import_test({'test_number': 1, 'title': 'Bad', 'modules': [None]})
        self.assertFalse(IELTSMockTest.objects.exists())
