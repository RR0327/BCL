"""Release tooling regression tests: no writes to live application data."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase
from django.db import connections
from io import StringIO
import hashlib
import json
import sqlite3

class ReleaseCheckTests(TestCase):
    def test_local_preflight_generates_machine_readable_report(self):
        with TemporaryDirectory() as temp:
            report = Path(temp) / 'preflight.json'
            output = StringIO()
            call_command('release_check', output=str(report), stdout=output)
            data = json.loads(report.read_text(encoding='utf-8'))
            self.assertTrue(data['passed'])
            self.assertFalse(data['strict'])
            self.assertTrue(any(x['name'] == 'migrations_applied' for x in data['checks']))
    def test_strict_mode_blocks_insecure_local_configuration(self):
        with self.assertRaises(CommandError):
            call_command('release_check', strict=True, stdout=StringIO())

class SQLiteBackupTests(TestCase):
    def test_backup_produces_verified_snapshot_and_manifest(self):
        if connections['default'].vendor != 'sqlite':
            self.skipTest('SQLite-specific test')
        with TemporaryDirectory() as temp:
            with patch('bcl.management.commands.backup_sqlite.connections') as mock_connections:
                # Back up a standalone fixture, not Django's active test database.
                src = Path(temp) / 'source.sqlite3'
                with sqlite3.connect(str(src)) as db:
                    db.execute('CREATE TABLE demo (value TEXT)')
                    db.execute('INSERT INTO demo VALUES (?)', ('example',))
                mock_connections.__getitem__.return_value.vendor = 'sqlite'
                mock_connections.__getitem__.return_value.settings_dict = {'NAME': str(src)}
                destination = Path(temp).parent / ('backup_test_' + src.parent.name)
                try:
                    call_command('backup_sqlite', destination=str(destination), stdout=StringIO())
                    files = list(destination.glob('*.sqlite3'))
                    self.assertEqual(len(files), 1)
                    manifest = json.loads(files[0].with_suffix('.json').read_text())
                    self.assertEqual(manifest['sha256'], hashlib.sha256(files[0].read_bytes()).hexdigest())
                    with sqlite3.connect(str(files[0])) as db:
                        self.assertEqual(db.execute('SELECT value FROM demo').fetchone()[0], 'example')
                finally:
                    import shutil
                    shutil.rmtree(destination, ignore_errors=True)
    def test_rejects_non_sqlite_engine(self):
        with patch('bcl.management.commands.backup_sqlite.connections') as con:
            con.__getitem__.return_value.vendor = 'postgresql'
            with self.assertRaises(CommandError):
                call_command('backup_sqlite', destination='unused-backups', stdout=StringIO())
