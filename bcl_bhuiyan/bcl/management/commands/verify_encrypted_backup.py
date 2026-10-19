"""Validate encrypted backup and SQLite integrity without restoring into live database."""
import hashlib
import json
import os
import sqlite3
import tempfile
from pathlib import Path
from cryptography.fernet import Fernet, InvalidToken
from django.core.management.base import BaseCommand, CommandError

class Command(BaseCommand):
    help = 'Verify encrypted backup manifest, decryption and SQLite integrity; does not restore.'

    def add_arguments(self, parser):
        parser.add_argument('--manifest', required=True)

    def handle(self, *args, **options):
        manifest_path = Path(options['manifest']).resolve()
        try:
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            filename = manifest['file']
            if Path(filename).name != filename:
                raise ValueError('Invalid backup filename')
            ciphertext = (manifest_path.parent / filename).read_bytes()
            if hashlib.sha256(ciphertext).hexdigest() != manifest['sha256']:
                raise CommandError('SHA-256 mismatch')
            data = Fernet(os.environ['IELTS_BACKUP_FERNET_KEY'].encode('ascii')).decrypt(ciphertext)
        except (KeyError, ValueError, InvalidToken, OSError) as exc:
            raise CommandError(f'Backup verification failed: {exc}') from exc
        with tempfile.NamedTemporaryFile(suffix='.sqlite3', delete=False) as tmp:
            temporary_path = Path(tmp.name)
            tmp.write(data)
        try:
            with sqlite3.connect(str(temporary_path)) as connection:
                status = connection.execute('PRAGMA integrity_check').fetchone()[0]
                if status != 'ok':
                    raise CommandError(f'SQLite integrity check failed: {status}')
        finally:
            temporary_path.unlink(missing_ok=True)
        self.stdout.write(self.style.SUCCESS('Backup verified: SHA-256, decryption, SQLite integrity.'))
