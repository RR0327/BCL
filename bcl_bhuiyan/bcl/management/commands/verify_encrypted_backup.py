"""Validate Fernet backup, SHA-256 and SQLite integrity without touching the live database."""
import hashlib
import json
import os
import sqlite3
import tempfile
from pathlib import Path
from cryptography.fernet import Fernet, InvalidToken
from django.core.management.base import BaseCommand, CommandError

class Command(BaseCommand):
    help = 'Verify encrypted SQLite backup without restoring it.'

    def add_arguments(self, parser):
        parser.add_argument('--manifest', required=True)

    def handle(self, *args, **options):
        manifest_path = Path(options['manifest']).expanduser().resolve()
        try:
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            filename = manifest['file']
            if not isinstance(filename, str) or filename in ('.', '..') or Path(filename).name != filename or '\\' in filename or '/' in filename:
                raise ValueError('Invalid backup filename')
            ciphertext = (manifest_path.parent / filename).read_bytes()
            if hashlib.sha256(ciphertext).hexdigest() != manifest['sha256']:
                raise CommandError('SHA-256 mismatch')
            fernet = Fernet(os.environ['IELTS_BACKUP_FERNET_KEY'].encode('ascii'))
            data = fernet.decrypt(ciphertext)
        except (KeyError, ValueError, InvalidToken, OSError, UnicodeEncodeError) as exc:
            raise CommandError('Backup verification failed (manifest, key, or ciphertext invalid)') from exc
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix='.sqlite3', delete=False) as tmp:
                tmp_path = Path(tmp.name)
                tmp.write(data)
            connection = sqlite3.connect(str(tmp_path))
            try:
                status = connection.execute('PRAGMA integrity_check').fetchone()[0]
                if status != 'ok':
                    raise CommandError('SQLite integrity check failed: ' + status)
            finally:
                connection.close()
        finally:
            if tmp_path is not None:
                tmp_path.unlink(missing_ok=True)
        self.stdout.write(self.style.SUCCESS('Backup verified: SHA-256, decryption, SQLite integrity.'))
