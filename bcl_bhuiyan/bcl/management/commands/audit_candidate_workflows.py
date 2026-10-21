"""Read-only candidate-attempt consistency audit; no personal records in output."""
import json
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.models import Count, F, Q
from django.utils import timezone
from bcl.models import CandidateAttempt, CandidateAnswer, ExamModule


def audit_candidate_workflows(now=None):
    """Return aggregate counts; never expose candidate identifiers or answer text."""
    now = now or timezone.now()
    attempts = CandidateAttempt.objects.all()
    answers = CandidateAnswer.objects.all()
    active = CandidateAttempt.AttemptStatus.IN_PROGRESS
    closed = [CandidateAttempt.AttemptStatus.SUBMITTED, CandidateAttempt.AttemptStatus.AUTO_SUBMITTED]
    anomalies = {
        'expired_in_progress': attempts.filter(status=active, expires_at__lte=now).count(),
        'closed_missing_submission_time': attempts.filter(status__in=closed, submitted_at__isnull=True).count(),
        'active_with_submission_time': attempts.filter(status=active, submitted_at__isnull=False).count(),
        'answer_from_different_module': answers.exclude(question__section__module_id=F('attempt__module_id')).count(),
        'awarded_marks_exceed_question': answers.filter(awarded_marks__gt=F('question__marks')).count(),
        'closed_objective_attempt_missing_score': attempts.filter(status__in=closed, module__module_type__in=[ExamModule.ModuleType.READING, ExamModule.ModuleType.LISTENING], raw_score__isnull=True).count(),
    }
    active_groups = attempts.filter(status=active).values('candidate_id','module_id').annotate(n=Count('pk')).filter(n__gt=1)
    anomalies['duplicate_active_attempt_groups'] = active_groups.count()
    return {
        'database_engine': connection.vendor,
        'generated_at': now.isoformat(),
        'totals': {'attempts': attempts.count(), 'answers': answers.count(), 'in_progress': attempts.filter(status=active).count()},
        'anomalies': anomalies,
        'passed': all(count == 0 for count in anomalies.values()),
        'notes': ['Expired in-progress attempts are closed lazily on candidate requests; an expired count may require operational follow-up.', 'Aggregate audit only; no records are changed.'],
    }


class Command(BaseCommand):
    help = 'Read-only aggregate integrity audit for candidate exam attempts and answers.'

    def add_arguments(self, parser):
        parser.add_argument('--require-postgres', action='store_true')
        parser.add_argument('--output', help='Optional JSON report path')
        parser.add_argument('--fail-on-anomaly', action='store_true')

    def handle(self, *args, **options):
        if options['require_postgres'] and connection.vendor != 'postgresql':
            raise CommandError('PostgreSQL is required; refusing to audit a different database engine.')
        report = audit_candidate_workflows()
        rendered = json.dumps(report, indent=2)
        if options['output']:
            output = Path(options['output'])
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(rendered + '\n', encoding='utf-8')
        self.stdout.write(rendered)
        if options['fail_on_anomaly'] and not report['passed']:
            raise CommandError('Candidate workflow audit found consistency anomalies; see JSON report.')
