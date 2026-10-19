"""Encrypted, consistent SQLite backup. No plaintext snapshots in backup destination."""
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
    help = 'Create a Fernet-encrypted SQLite snapshot with SHA-256 manifest.'

    def add_arguments(self, parser):
        parser.add_argument('--destination', required=True)

    def handle(self, *args, **options):
        cfg = settings.DATABASES['default']
        if cfg['ENGINE'] != 'django.db.backends.sqlite3':
            raise CommandError('SQLite only; use pg_dump for PostgreSQL.')
        try:
            fernet = Fernet(os.environ.get('IELTS_BACKUP_FERNET_KEY', '').encode('ascii'))
        except (ValueError, TypeError, UnicodeEncodeError) as exc:
            raise CommandError('Set a valid IELTS_BACKUP_FERNET_KEY outside the repository.') from exc
        source = Path(cfg['NAME']).expanduser().resolve()
        if not source.is_file():
            raise CommandError('SQLite source database does not exist')
        destination = Path(options['destination']).expanduser().resolve()
        base = Path(settings.BASE_DIR).resolve()
        if destination == base or base in destination.parents or destination == source.parent:
            raise CommandError('Backup destination must be outside the application tree')
        destination.mkdir(parents=True, exist_ok=True)
        stamp = timezone.now().strftime('%Y%m%dT%H%M%S%fZ')
        tmp_path = None
        target = None
        manifest_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix='.sqlite3', delete=False) as tmp:
                tmp_path = Path(tmp.name)
            origin = sqlite3.connect(str(source))
            try:
                snapshot = sqlite3.connect(str(tmp_path))
                try:
                    origin.backup(snapshot)
                    status = snapshot.execute('PRAGMA integrity_check').fetchone()[0]
                    if status != 'ok':
                        raise CommandError('SQLite snapshot failed integrity check')
                finally:
                    snapshot.close()
            finally:
                origin.close()
            ciphertext = fernet.encrypt(tmp_path.read_bytes())
            name = 'ielts_' + stamp
            target = destination / (name + '.sqlite3.enc')
            with target.open('xb') as output:
                output.write(ciphertext)
            os.chmod(target, 0o600)
            manifest = {'file': target.name, 'sha256': hashlib.sha256(ciphertext).hexdigest(),
                        'created_utc': timezone.now().isoformat(), 'encryption': 'Fernet',
                        'source': 'sqlite3', 'bytes': len(ciphertext)}
            manifest_path = destination / (name + '.manifest.json')
            with manifest_path.open('x', encoding='utf-8') as out:
                json.dump(manifest, out, indent=2)
            os.chmod(manifest_path, 0o600)
            self.stdout.write(self.style.SUCCESS('Encrypted backup: ' + str(target)))
        except Exception:
            if manifest_path is None or not manifest_path.exists():
                if target is not None:
                    target.unlink(missing_ok=True)
            raise
        finally:
            if tmp_path is not None:
                tmp_path.unlink(missing_ok=True)
