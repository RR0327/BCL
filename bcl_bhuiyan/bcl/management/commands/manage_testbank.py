import json
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ValidationError
from django.db import transaction
from bcl.models import IELTSMockTest
from bcl.testbank import import_test, readiness

class Command(BaseCommand):
    help = 'Initialize empty slots, import authorized JSON test content, or audit readiness.'

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument('--initialize', action='store_true', help='Create missing unpublished test slots 1–30')
        group.add_argument('--audit', action='store_true', help='Check readiness of all test slots')
        group.add_argument('--import-json', metavar='FILE', help='Import one new test from a JSON file')
        parser.add_argument('--publish', action='store_true', help='Publish only if imported test is complete')
        parser.add_argument('--dry-run', action='store_true', help='Roll back changes after validation')

    def handle(self, *args, **options):
        if options['publish'] and not options['import_json']:
            raise CommandError('--publish requires --import-json')
        try:
            with transaction.atomic():
                if options['initialize']:
                    for number in range(1, 31):
                        _, created = IELTSMockTest.objects.get_or_create(test_number=number, defaults={'title': f'IELTS Mock Test {number}', 'is_published': False})
                        if created:
                            self.stdout.write(f'Created unpublished slot {number}')
                elif options['import_json']:
                    path = Path(options['import_json'])
                    data = json.loads(path.read_text(encoding='utf-8'))
                    test = import_test(data, publish=options['publish'])
                    self.stdout.write(f'Imported test {test.test_number}; published={test.is_published}')
                else:
                    for test in IELTSMockTest.objects.all():
                        issues = readiness(test)
                        self.stdout.write(f'Test {test.test_number}: {"READY" if not issues else "NOT READY"} ({len(issues)} issues)')
                        for issue in issues:
                            self.stdout.write('  - ' + issue)
                if options['dry_run']:
                    transaction.set_rollback(True)
                    self.stdout.write('DRY RUN: changes rolled back')
        except (ValidationError, ValueError, KeyError, OSError, json.JSONDecodeError) as exc:
            raise CommandError(str(exc)) from exc
