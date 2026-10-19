"""Dry-run-by-default retention purge; explicitly deletes only completed attempts."""
from datetime import timedelta
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from bcl.models import CandidateAttempt
from bcl.privacy import audit

class Command(BaseCommand):
    help = 'List or delete completed candidate attempts older than retention threshold. Default: dry run.'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, required=True)
        parser.add_argument('--execute', action='store_true')
        parser.add_argument('--confirm', default='')
        parser.add_argument('--batch-size', type=int, default=100)

    def handle(self, *args, **options):
        days = options['days']
        if days < 1 or options['batch_size'] < 1:
            raise CommandError('--days and --batch-size must be positive')
        if options['execute'] and options['confirm'] != 'DELETE-COMPLETED-ATTEMPTS':
            raise CommandError('Explicit --confirm DELETE-COMPLETED-ATTEMPTS required')
        cutoff = timezone.now() - timedelta(days=days)
        statuses = [CandidateAttempt.AttemptStatus.SUBMITTED, CandidateAttempt.AttemptStatus.AUTO_SUBMITTED, CandidateAttempt.AttemptStatus.EXPIRED]
        eligible = CandidateAttempt.objects.filter(status__in=statuses, submitted_at__lt=cutoff)
        total = eligible.count()
        self.stdout.write(f'Eligible completed attempts: {total}; cutoff: {cutoff.isoformat()}')
        if not options['execute']:
            self.stdout.write('DRY RUN: no records deleted. Candidate accounts are never deleted.')
            return
        removed = 0
        while True:
            with transaction.atomic():
                ids = list(CandidateAttempt.objects.filter(status__in=statuses, submitted_at__lt=cutoff).order_by('pk').values_list('pk', flat=True)[:options['batch_size']])
                if not ids:
                    break
                # PROTECT relationships can legitimately block deletion; rollback and report.
                CandidateAttempt.objects.filter(pk__in=ids).delete()
                removed += len(ids)
        audit('retention.purge', object_id=removed)
        self.stdout.write(self.style.SUCCESS(f'Deleted {removed} completed attempts.'))
