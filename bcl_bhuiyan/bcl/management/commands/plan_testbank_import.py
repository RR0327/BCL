"""Read-only import readiness: JSON structural checks plus destination-slot safety."""
import json
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from bcl.models import IELTSMockTest
from bcl.management.commands.preflight_testbank import validate_payload


def build_import_plan(payload, slot):
    issues = validate_payload(payload)
    if isinstance(payload, dict) and isinstance(payload.get('test_number'), int):
        if slot is not None:
            if slot.is_published:
                issues.append('Destination test is published; import prohibited')
            if slot.modules.exists():
                issues.append('Destination test has modules; import prohibited')
            # Attempts cannot exist without a module in the current schema.
    return {
        'test_number': payload.get('test_number') if isinstance(payload, dict) else None,
        'slot_status': ('absent' if slot is None else 'published' if slot.is_published else 'populated' if slot.modules.exists() else 'empty_unpublished'),
        'import_eligible': not issues,
        'issues': issues,
        'manual_requirements': [
            'Confirm rights to all passages, questions and answer keys',
            'Upload and test Listening audio through admin after import',
            'Review Writing tasks and marking rubric',
            'Run staging candidate end-to-end tests before publication',
        ],
    }


class Command(BaseCommand):
    help = 'Read-only assessment of structural validity and safe destination-slot import eligibility.'

    def add_arguments(self, parser):
        parser.add_argument('--file', required=True)
        parser.add_argument('--output', help='Optional report JSON file')
        parser.add_argument('--require-postgres', action='store_true')

    def handle(self, *args, **options):
        from django.db import connection
        if options['require_postgres'] and connection.vendor != 'postgresql':
            raise CommandError('PostgreSQL required for this staging audit')
        try:
            payload = json.loads(Path(options['file']).read_text(encoding='utf-8'))
        except (OSError, ValueError) as exc:
            raise CommandError(f'Cannot read test bank JSON: {exc}') from exc
        number = payload.get('test_number') if isinstance(payload, dict) else None
        slot = IELTSMockTest.objects.filter(test_number=number).first() if type(number) is int and 1 <= number <= 30 else None
        plan = build_import_plan(payload, slot)
        report = json.dumps(plan, indent=2)
        if options['output']:
            target = Path(options['output'])
            if not target.parent.is_dir():
                raise CommandError('Report directory does not exist')
            try:
                target.write_text(report + '\n', encoding='utf-8')
            except OSError as exc:
                raise CommandError(f'Cannot write report: {exc}') from exc
        self.stdout.write(report)
        if not plan['import_eligible']:
            raise CommandError(f'Import plan blocked by {len(plan["issues"])} issue(s)')
