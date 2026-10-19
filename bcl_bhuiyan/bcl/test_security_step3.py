"""Privacy and recovery regression tests; designed for Django TestCase isolation."""
from datetime import timedelta
from io import StringIO
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone
from bcl.models import CandidateAttempt, ExamModule, IELTSMockTest, SecurityAuditEvent

class PrivacyTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='privacycandidate', password='StrongPass123!')
        self.test = IELTSMockTest.objects.create(title='Privacy test', test_number=29)
        self.module = ExamModule.objects.create(mock_test=self.test, module_type='reading')
        self.old = CandidateAttempt.objects.create(candidate=self.user, module=self.module,
            status='submitted', started_at=timezone.now()-timedelta(days=90),
            expires_at=timezone.now()-timedelta(days=89), submitted_at=timezone.now()-timedelta(days=89))
        self.active = CandidateAttempt.objects.create(candidate=self.user, module=self.module,
            status='in_progress', expires_at=timezone.now()+timedelta(minutes=60))

    def test_purge_defaults_to_dry_run(self):
        call_command('purge_candidate_data', days=30, stdout=StringIO())
        self.assertTrue(CandidateAttempt.objects.filter(pk=self.old.pk).exists())

    def test_purge_requires_confirmation(self):
        with self.assertRaises(CommandError):
            call_command('purge_candidate_data', days=30, execute=True, stdout=StringIO())

    def test_purge_only_completed_old_attempts(self):
        call_command('purge_candidate_data', days=30, execute=True,
                     confirm='DELETE-COMPLETED-ATTEMPTS', stdout=StringIO())
        self.assertFalse(CandidateAttempt.objects.filter(pk=self.old.pk).exists())
        self.assertTrue(CandidateAttempt.objects.filter(pk=self.active.pk).exists())
        self.assertTrue(get_user_model().objects.filter(pk=self.user.pk).exists())
        self.assertTrue(SecurityAuditEvent.objects.filter(event='retention.purge').exists())

    def test_invalid_retention_rejected(self):
        with self.assertRaises(CommandError):
            call_command('purge_candidate_data', days=0, stdout=StringIO())

    def test_login_audit_records_no_password(self):
        self.client.post(__import__('django.urls', fromlist=['reverse']).reverse('bcl:login'), {'username': 'privacycandidate', 'password': 'StrongPass123!'})
        self.assertTrue(SecurityAuditEvent.objects.filter(event='auth.login', actor_id=self.user.pk).exists())
        self.assertFalse(any('StrongPass123!' in str(event) for event in SecurityAuditEvent.objects.all()))

    def test_invalid_backup_key_rejected(self):
        from unittest.mock import patch
        with patch.dict('os.environ', {'IELTS_BACKUP_FERNET_KEY': 'bad'}):
            with self.assertRaises(CommandError):
                call_command('encrypted_backup', destination='/tmp/backup_test_invalid', stdout=StringIO())
