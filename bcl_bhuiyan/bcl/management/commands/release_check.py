"""Non-destructive deployment preflight. No database records are modified."""
from django.core.management.base import BaseCommand
from django.conf import settings
from django.core.checks import run_checks, Tags
from django.db import connections
from django.db.migrations.executor import MigrationExecutor
from pathlib import Path
import json

class Command(BaseCommand):
    help = 'Inspect release configuration, pending migrations and database availability; emits JSON.'

    def add_arguments(self, parser):
        parser.add_argument('--strict', action='store_true', help='Fail if production prerequisites are missing')
        parser.add_argument('--output', type=str, help='Write JSON report to a chosen path')

    def handle(self, *args, **opts):
        checks = []
        def record(name, ok, detail, production_only=False):
            checks.append({'name': name, 'passed': bool(ok), 'detail': detail,
                           'production_only': production_only})
        record('debug_disabled', not settings.DEBUG, 'DEBUG must be False in production', True)
        record('explicit_hosts', bool(settings.ALLOWED_HOSTS) and '*' not in settings.ALLOWED_HOSTS,
               'ALLOWED_HOSTS must enumerate approved domains', True)
        record('secure_session_cookie', settings.SESSION_COOKIE_SECURE,
               'Secure session cookies require HTTPS', True)
        record('secure_csrf_cookie', settings.CSRF_COOKIE_SECURE,
               'Secure CSRF cookies require HTTPS', True)
        record('https_redirect', settings.SECURE_SSL_REDIRECT,
               'HTTPS redirect should be enabled behind a correctly configured proxy', True)
        record('postgresql', connections['default'].vendor == 'postgresql',
               'PostgreSQL required for the intended production deployment', True)
        record('media_not_static', Path(settings.MEDIA_ROOT).resolve() != Path(settings.STATIC_ROOT).resolve(),
               'Uploaded media must not share the static files directory')
        record('media_access_review', False,
               'Exam media access controls require a separate manual review', True)
        try:
            connections['default'].ensure_connection()
            record('database_connection', True, 'Database connection succeeded')
            executor = MigrationExecutor(connections['default'])
            targets = executor.loader.graph.leaf_nodes()
            pending = executor.migration_plan(targets)
            record('migrations_applied', not pending,
                   'Pending migration count: %d' % len(pending))
        except Exception as exc:
            record('database_connection', False, '%s: %s' % (type(exc).__name__, str(exc)[:240]))
        try:
            issues = run_checks(tags=[Tags.security], include_deployment_checks=True)
            errors = [str(x) for x in issues if x.is_serious()]
            record('django_security_checks', not errors,
                   'No serious Django security errors' if not errors else '; '.join(errors)[:500], True)
        except Exception as exc:
            record('django_security_checks', False, str(exc)[:240], True)
        strict = opts['strict']
        relevant = [x for x in checks if strict or not x['production_only']]
        passed = all(x['passed'] for x in relevant)
        report = {'passed': passed, 'strict': strict, 'checks': checks,
                  'warning': 'This is a preflight, not a penetration test or deployment approval.'}
        output = json.dumps(report, indent=2)
        if opts['output']:
            target = Path(opts['output']).expanduser().resolve()
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(output + '\n', encoding='utf-8')
        self.stdout.write(output)
        if not passed:
            from django.core.management.base import CommandError
            raise CommandError('Release preflight failed; review the JSON report.')
