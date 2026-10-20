"""Consistent local SQLite snapshot using sqlite3 backup API (not for PostgreSQL)."""
from django.core.management.base import BaseCommand, CommandError
from django.db import connections
from pathlib import Path
from datetime import datetime, timezone
import sqlite3
import hashlib
import json

class Command(BaseCommand):
    help = 'Back up a local SQLite database with a SHA-256 manifest; never overwrites files.'

    def add_arguments(self, parser):
        parser.add_argument('--destination', required=True, help='Directory outside the repository')

    def handle(self, *args, **options):
        conn = connections['default']
        if conn.vendor != 'sqlite':
            raise CommandError('Only SQLite is supported; use pg_dump for PostgreSQL.')
        source = Path(conn.settings_dict['NAME']).resolve()
        if not source.is_file():
            raise CommandError('SQLite source database not found')
        dest = Path(options['destination']).expanduser().resolve()
        if dest == source.parent or source.parent in dest.parents:
            raise CommandError('Backup destination must be outside the project database directory')
        dest.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        target = dest / ('ielts-sqlite-' + stamp + '.sqlite3')
        origin = sqlite3.connect(str(source))
        backup = sqlite3.connect(str(target))
        try:
            origin.backup(backup)
        finally:
            backup.close()
            origin.close()
        verify = sqlite3.connect(str(target))
        try:
            status = verify.execute('PRAGMA integrity_check').fetchone()[0]
        finally:
            verify.close()
        if status != 'ok':
            target.unlink(missing_ok=True)
            raise CommandError('Backup integrity check failed')
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        manifest = {'filename': target.name, 'sha256': digest, 'integrity_check': status,
                    'created_utc': stamp, 'size_bytes': target.stat().st_size}
        target.with_suffix('.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
        self.stdout.write('Verified backup: ' + str(target))
        self.stdout.write('SHA-256: ' + digest)
