"""Read-only verification of examination assets and answer-key consistency.

This audit deliberately does not print question text, answers, media paths, or
candidate data. Storage existence checks are opt-in because remote backends may
require network access and permissions.
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from bcl.models import IELTSMockTest, ExamModule, Question
from bcl.testbank import readiness


class Command(BaseCommand):
    help = 'Audit published exam content and media without changing records or exposing answer keys.'

    def add_arguments(self, parser):
        parser.add_argument('--output', help='Write aggregate JSON report to this path')
        parser.add_argument('--require-postgres', action='store_true')
        parser.add_argument('--verify-storage', action='store_true', help='Check referenced media objects exist in configured storage')
        parser.add_argument('--strict', action='store_true', help='Exit nonzero when any published test has issues')

    def handle(self, *args, **options):
        if options['require_postgres'] and connection.vendor != 'postgresql':
            raise CommandError(f'PostgreSQL required; current database is {connection.vendor}')

        findings = []
        published_count = 0
        checked_audio = 0
        checked_images = 0
        for test in IELTSMockTest.objects.prefetch_related('modules__sections__questions__options').order_by('test_number'):
            if not test.is_published:
                continue
            published_count += 1
            problems = list(readiness(test))
            for module in test.modules.all():
                for section in module.sections.all():
                    for field_name in ('audio_file', 'image'):
                        field = getattr(section, field_name)
                        if not field:
                            continue
                        if field_name == 'audio_file':
                            checked_audio += 1
                        else:
                            checked_images += 1
                        if options['verify_storage']:
                            try:
                                exists = field.storage.exists(field.name)
                            except Exception:
                                problems.append(f'{module.module_type} section {section.order}: {field_name} storage check failed')
                            else:
                                if not exists:
                                    problems.append(f'{module.module_type} section {section.order}: {field_name} object missing')
                    for question in section.questions.all():
                        if question.question_type == Question.QuestionType.MCQ:
                            options_list = list(question.options.all())
                            if len(options_list) < 2:
                                problems.append(f'{module.module_type} section {section.order} question {question.order}: fewer than two MCQ options')
                            if question.correct_answer.strip() and question.correct_answer.strip() not in {o.option_key for o in options_list}:
                                problems.append(f'{module.module_type} section {section.order} question {question.order}: canonical key not among options')
                        if question.marks < 1:
                            problems.append(f'{module.module_type} section {section.order} question {question.order}: nonpositive marks')
            if problems:
                findings.append({'test_number': test.test_number, 'issues': sorted(set(problems))})

        report = {
            'database_vendor': connection.vendor,
            'published_tests_checked': published_count,
            'published_tests_with_issues': len(findings),
            'audio_references_checked': checked_audio,
            'image_references_checked': checked_images,
            'storage_existence_verified': bool(options['verify_storage']),
            'findings': findings,
            'manual_checks_required': [
                'Confirm licensing and factual accuracy of all examination content',
                'Test audio playback and media authorization in a real browser',
                'Validate writing marking and candidate end-to-end workflows',
            ],
        }
        output = json.dumps(report, indent=2, ensure_ascii=False)
        self.stdout.write(output)
        if options['output']:
            path = Path(options['output'])
            if not path.parent.is_dir():
                raise CommandError(f'Output directory does not exist: {path.parent}')
            path.write_text(output + '\n', encoding='utf-8')
        if options['strict'] and findings:
            raise CommandError(f'{len(findings)} published test(s) failed asset integrity audit')
