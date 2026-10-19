"""Consistent SQLite snapshot encrypted with Fernet; plaintext temporary file removed."""
import hashlib
import json
import os
import sqlite3
import tempfile
from pathlib import Path
from cryptography.fernet import Fernet
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

class Command(BaseCommand):
    help = 'Create an encrypted SQLite backup with SHA-256 manifest; key is never saved in backup folder.'

    def add_arguments(self, parser):
        parser.add_argument('--destination', required=True)

    def handle(self, *args, **options):
        cfg = settings.DATABASES['default']
        if cfg['ENGINE'] != 'django.db.backends.sqlite3':
            raise CommandError('SQLite only. For PostgreSQL use pg_dump with encryption and tested restore.')
        key = os.environ.get('IELTS_BACKUP_FERNET_KEY', '')
        try:
            fernet = Fernet(key.encode('ascii'))
        except Exception as exc:
            raise CommandError('Set IELTS_BACKUP_FERNET_KEY to a valid Fernet key stored outside the repository.') from exc
        source = Path(cfg['NAME'])
        if not source.is_file():
            raise CommandError('SQLite source database does not exist')
        destination = Path(options['destination']).expanduser().resolve()
        if destination == source.parent or source.parent in destination.parents:
            raise CommandError('Backup destination must be outside the application tree')
        destination.mkdir(parents=True, exist_ok=True)
        name = 'ielts_' + timezone.now().strftime('%Y%m%dT%H%M%S%fZ')
        tmp = None
        try:
            with tempfile.NamedTemporaryFile(suffix='.sqlite3', delete=False) as handle:
                tmp = Path(handle.name)
            
            src = sqlite3.connect(str(source))
            try:
                dst = sqlite3.connect(str(tmp))
                try:
                    src.backup(dst)
                finally:
                    dst.close()
            finally:
                src.close()

            encrypted = fernet.encrypt(tmp.read_bytes())
            target = destination / (name + '.sqlite3.enc')
            with target.open('xb') as output:
                output.write(encrypted)
            os.chmod(target, 0o600)
            manifest = {'file': target.name, 'sha256': hashlib.sha256(encrypted).hexdigest(),
                        'created_utc': timezone.now().isoformat(), 'encryption': 'Fernet', 'source': 'sqlite3'}
            manifest_path = destination / (name + '.manifest.json')
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
            os.chmod(manifest_path, 0o600)
            self.stdout.write(self.style.SUCCESS(f'Encrypted backup: {target}'))
        finally:
            if tmp is not None:
                tmp.unlink(missing_ok=True)
