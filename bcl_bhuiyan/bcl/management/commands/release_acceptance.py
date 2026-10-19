"""Read-only release acceptance: test-bank completeness and critical production controls."""
import json
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from bcl.models import IELTSMockTest
from bcl.testbank import readiness

class Command(BaseCommand):
    help = 'Produce JSON release acceptance report. Strict mode refuses incomplete or unsafe releases.'

    def add_arguments(self, parser):
        parser.add_argument('--output', required=True)
        parser.add_argument('--strict', action='store_true')

    def handle(self, *args, **options):
        tests = {t.test_number: t for t in IELTSMockTest.objects.prefetch_related('modules__sections__questions__options').all() if 1 <= t.test_number <= 30}
        rows = []
        for n in range(1, 31):
            t = tests.get(n)
            issues = ['test slot missing'] if t is None else readiness(t)
            if t is not None and not t.is_published:
                issues.append('not published')
            rows.append({'test_number': n, 'ready': not issues, 'issues': issues})
        controls = {'debug_disabled': not settings.DEBUG,
                    'https_redirect': bool(settings.SECURE_SSL_REDIRECT),
                    'secure_session_cookie': bool(settings.SESSION_COOKIE_SECURE),
                    'secure_csrf_cookie': bool(settings.CSRF_COOKIE_SECURE),
                    'postgresql': settings.DATABASES['default']['ENGINE'] == 'django.db.backends.postgresql'}
        report = {'test_bank': rows, 'controls': controls,
                  'automated_gates_pass': all(x['ready'] for x in rows) and all(controls.values()),
                  'manual_gates': ['content licensing', 'private media reverse-proxy validation',
                                   'MFA recovery', 'PostgreSQL restore and data validation',
                                   'browser E2E', 'independent security review', 'backup encryption and retention policy']}
        out = Path(options['output']).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2), encoding='utf-8')
        self.stdout.write('Release acceptance report: ' + str(out))
        if options['strict'] and not report['automated_gates_pass']:
            raise CommandError('Release blocked: automated gates failed; inspect report')
