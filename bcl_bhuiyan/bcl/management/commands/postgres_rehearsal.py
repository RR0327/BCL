"""PostgreSQL backup and isolated restore rehearsal with explicit destructive-action gate."""
import json
import os
import shutil
import subprocess
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

class Command(BaseCommand):
    help = 'Back up PostgreSQL and optionally restore into a separate existing staging database.'

    def add_arguments(self, parser):
        parser.add_argument('--destination', required=True)
        parser.add_argument('--restore-db', help='Existing EMPTY staging database name, never the source database')
        parser.add_argument('--execute-restore', action='store_true')
        parser.add_argument('--confirm', default='')

    def handle(self, *args, **options):
        cfg = settings.DATABASES['default']
        if cfg['ENGINE'] != 'django.db.backends.postgresql':
            raise CommandError('Requires PostgreSQL as the configured default database')
        if not shutil.which('pg_dump') or not shutil.which('pg_restore'):
            raise CommandError('pg_dump and pg_restore must be installed and on PATH')
        dest = Path(options['destination']).expanduser().resolve()
        base = Path(settings.BASE_DIR).resolve()
        if dest == base or base in dest.parents:
            raise CommandError('Destination must be outside the repository')
        source = str(cfg['NAME'])
        restore = options.get('restore_db')
        if restore and (restore == source or not restore.strip()):
            raise CommandError('Restoration target must be a different, non-empty staging database name')
        if options['execute_restore'] and (not restore or options['confirm'] != 'RESTORE-ISOLATED-STAGING'):
            raise CommandError('Restore requires --restore-db and --confirm RESTORE-ISOLATED-STAGING')
        if restore and not options['execute_restore']:
            self.stdout.write('Restore preview only; use --execute-restore with explicit confirmation.')
        dest.mkdir(parents=True, exist_ok=True)
        dump = dest / ('ielts-postgres-' + timezone.now().strftime('%Y%m%dT%H%M%S%fZ') + '.dump')
        env = os.environ.copy()
        if cfg.get('PASSWORD'):
            env['PGPASSWORD'] = str(cfg['PASSWORD'])
        host = str(cfg.get('HOST') or 'localhost')
        port = str(cfg.get('PORT') or '5432')
        user = str(cfg.get('USER') or '')
        base_args = ['--host', host, '--port', port]
        if user:
            base_args += ['--username', user]
        def run(args):
            try:
                result = subprocess.run(args, env=env, capture_output=True, text=True, timeout=1800, check=False)
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise CommandError('PostgreSQL utility unavailable or timed out') from exc
            if result.returncode:
                raise CommandError('PostgreSQL utility failed; inspect database connectivity and permissions')
        try:
            run(['pg_dump', *base_args, '--format=custom', '--file', str(dump), source])
            run(['pg_restore', '--list', str(dump)])
            os.chmod(dump, 0o600)
            if options['execute_restore']:
                # Never use --clean or --create: target must be independently provisioned and empty.
                run(['pg_restore', *base_args, '--dbname', restore, '--exit-on-error', '--single-transaction', str(dump)])
            manifest = {'backup': dump.name, 'source': 'postgresql', 'restore_target': restore or '',
                        'restore_executed': bool(options['execute_restore']), 'created_utc': timezone.now().isoformat(),
                        'warning': 'Dump is not encrypted; encrypt and restrict access before retention.'}
            (dest / (dump.name + '.manifest.json')).write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        except Exception:
            dump.unlink(missing_ok=True)
            raise
        self.stdout.write(self.style.SUCCESS('PostgreSQL dump and archive inspection passed: ' + str(dump)))
        if options['execute_restore']:
            self.stdout.write(self.style.SUCCESS('Staging restore command succeeded; verify data and application separately.'))
