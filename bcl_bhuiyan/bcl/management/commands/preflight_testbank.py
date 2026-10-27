"""Validate a test-bank JSON payload without writing to the database."""
import json
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from bcl.models import Question
from bcl.testbank import MODULES, EXPECTED_SECTIONS, EXPECTED_QUESTIONS, QUESTION_TYPE_ALIASES

PLACEHOLDERS = ('insert ', 'placeholder', 'lorem ipsum', 'todo:')


def validate_payload(data):
    issues = []
    if not isinstance(data, dict):
        return ['Root must be a JSON object']
    try:
        number = int(data['test_number'])
        if number not in range(1, 31):
            issues.append('test_number must be 1 through 30')
    except (KeyError, ValueError, TypeError):
        issues.append('test_number must be an integer from 1 to 30')
    if not isinstance(data.get('title'), str) or not data['title'].strip():
        issues.append('Nonempty title required')
    modules = data.get('modules')
    if not isinstance(modules, list):
        return issues + ['modules must be an array']
    kinds = []
    for module in modules:
        if not isinstance(module, dict):
            issues.append('Each module must be an object')
            continue
        kind = module.get('module_type')
        if kind not in MODULES:
            issues.append(f'Unsupported module type: {kind}')
            continue
        kinds.append(kind)
        sections = module.get('sections')
        if not isinstance(sections, list):
            issues.append(f'{kind}: sections must be an array')
            continue
        if len(sections) != EXPECTED_SECTIONS[kind]:
            issues.append(f'{kind}: expected {EXPECTED_SECTIONS[kind]} sections, found {len(sections)}')
        count = 0
        for si, section in enumerate(sections, 1):
            label = f'{kind} section {si}'
            if not isinstance(section, dict):
                issues.append(f'{label}: must be an object')
                continue
            if kind == 'reading' and not _valid_text(section.get('passage')):
                issues.append(f'{label}: original passage required')
            questions = section.get('questions')
            if not isinstance(questions, list):
                issues.append(f'{label}: questions must be an array')
                continue
            count += len(questions)
            if kind == 'writing' and len(questions) != 1:
                issues.append(f'{label}: expected one essay task')
            for qi, question in enumerate(questions, 1):
                qlabel = f'{label} question {qi}'
                if not isinstance(question, dict):
                    issues.append(f'{qlabel}: must be an object')
                    continue
                raw_qtype = str(question.get('question_type', '')).strip().lower()
                qtype = QUESTION_TYPE_ALIASES.get(raw_qtype, raw_qtype)
                if qtype not in Question.QuestionType.values:
                    issues.append(f'{qlabel}: unsupported question type')
                if not _valid_text(question.get('question_text')):
                    issues.append(f'{qlabel}: substantive prompt required')
                if kind == 'writing':
                    if qtype != 'essay':
                        issues.append(f'{qlabel}: writing requires essay type')
                else:
                    if qtype == 'essay':
                        issues.append(f'{qlabel}: essay not allowed in auto-scored module')
                    options = question.get('options', [])
                    if not isinstance(options, list):
                        issues.append(f'{qlabel}: options must be an array')
                        continue
                    keys = [o.get('option_key') for o in options if isinstance(o, dict)]
                    if len(keys) != len(options) or len(keys) != len(set(keys)):
                        issues.append(f'{qlabel}: option keys must be unique and nonempty')
                    if any(not isinstance(o, dict) or not o.get('option_key') for o in options):
                        issues.append(f'{qlabel}: invalid option')
                    correct = sum(o.get('is_correct') is True for o in options if isinstance(o, dict))
                    if qtype == 'mcq' and correct != 1:
                        issues.append(f'{qlabel}: MCQ requires exactly one correct option')
                    if qtype in ('matching', 'matching_information') and correct == 0:
                        issues.append(f'{qlabel}: matching requires a correct option')
                    if not _valid_text(question.get('correct_answer')) and correct == 0:
                        issues.append(f'{qlabel}: answer key required')
        if count != EXPECTED_QUESTIONS[kind]:
            issues.append(f'{kind}: expected {EXPECTED_QUESTIONS[kind]} questions, found {count}')
    if len(kinds) != len(set(kinds)):
        issues.append('Module types must be unique')
    for kind in MODULES:
        if kind not in kinds:
            issues.append(f'{kind}: module missing')
    return issues


def _valid_text(value):
    return isinstance(value, str) and bool(value.strip()) and not value.strip().lower().startswith(PLACEHOLDERS)


class Command(BaseCommand):
    help = 'Read-only structural preflight of an authorized test-bank JSON file; listening audio checked separately.'

    def add_arguments(self, parser):
        parser.add_argument('--file', required=True, help='Local JSON payload')
        parser.add_argument('--output', help='Optional JSON report destination')

    def handle(self, *args, **options):
        try:
            data = json.loads(Path(options['file']).read_text(encoding='utf-8'))
        except (OSError, ValueError) as exc:
            raise CommandError(f'Cannot read test bank JSON: {exc}') from exc
        issues = validate_payload(data)
        report = {'structural_preflight_pass': not issues, 'issues': issues,
                  'requires_manual_checks': ['content licensing and factual review', 'listening audio upload and playback', 'writing rubric and browser end-to-end validation']}
        serialized = json.dumps(report, indent=2)
        if options.get('output'):
            output = Path(options['output'])
            if not output.parent.is_dir():
                raise CommandError('Report directory does not exist')
            output.write_text(serialized + '\n', encoding='utf-8')
        self.stdout.write(serialized)
        if issues:
            raise CommandError(f'Test bank preflight failed with {len(issues)} issue(s)')
