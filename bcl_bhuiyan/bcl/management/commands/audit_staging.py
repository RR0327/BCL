"""Read-only PostgreSQL staging and test-bank audit (no account data exported)."""
import json
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from bcl.models import IELTSMockTest, ExamModule, ExamSection, Question, CandidateAttempt, CandidateAnswer, WritingEvaluation
from bcl.testbank import readiness


class Command(BaseCommand):
    help = 'Read-only staging audit with aggregate counts and content readiness; no user records.'

    def add_arguments(self, parser):
        parser.add_argument('--output', type=str, help='Optional local JSON report path')
        parser.add_argument('--require-postgres', action='store_true', help='Fail unless connected to PostgreSQL')
        parser.add_argument('--strict', action='store_true', help='Fail when slots are missing or published tests are incomplete')

    def handle(self, *args, **options):
        vendor = connection.vendor
        if options['require_postgres'] and vendor != 'postgresql':
            raise CommandError(f'Expected PostgreSQL; active database is {vendor}')
        tests = list(IELTSMockTest.objects.prefetch_related('modules__sections__questions__options').order_by('test_number'))
        slot_numbers = {t.test_number for t in tests}
        missing = sorted(set(range(1, 31)) - slot_numbers)
        issues = []
        ready_count = 0
        for test in tests:
            problems = readiness(test)
            if not problems:
                ready_count += 1
            if test.is_published and problems:
                issues.append({'test_number': test.test_number, 'problems': problems})
        report = {
            'database_vendor': vendor,
            'counts': {
                'mock_tests': len(tests),
                'users': get_user_model().objects.count(),
                'modules': ExamModule.objects.count(),
                'sections': ExamSection.objects.count(),
                'questions': Question.objects.count(),
                'attempts': CandidateAttempt.objects.count(),
                'answers': CandidateAnswer.objects.count(),
                'writing_evaluations': WritingEvaluation.objects.count(),
            },
            'missing_test_slots': missing,
            'ready_tests': ready_count,
            'published_tests': sum(bool(t.is_published) for t in tests),
            'published_test_readiness_issues': issues,
        }
        output = json.dumps(report, indent=2, ensure_ascii=False)
        self.stdout.write(output)
        if options['output']:
            path = Path(options['output'])
            if not path.parent.is_dir():
                raise CommandError(f'Output directory does not exist: {path.parent}')
            path.write_text(output + '\n', encoding='utf-8')
        if options['strict'] and (missing or issues):
            raise CommandError('Staging audit failed: missing slots or incomplete published tests')
