"""Minimal metadata-only security audit logging. Never store credentials or answers."""
from django.db import models
from django.utils import timezone

class SecurityAuditEvent(models.Model):
    occurred_at = models.DateTimeField(default=timezone.now, db_index=True)
    event = models.CharField(max_length=64, db_index=True)
    actor_id = models.PositiveBigIntegerField(null=True, blank=True)
    subject_id = models.PositiveBigIntegerField(null=True, blank=True)
    object_id = models.PositiveBigIntegerField(null=True, blank=True)
    outcome = models.CharField(max_length=16, default='success')

    class Meta:
        ordering = ['-occurred_at']

    def __str__(self):
        return f'{self.event} at {self.occurred_at.isoformat()}'


def audit(event, *, actor=None, subject=None, object_id=None, outcome='success'):
    """Store only identifiers; do not log IPs, answers, passwords or MFA tokens."""
    return SecurityAuditEvent.objects.create(event=event, actor_id=getattr(actor, 'pk', actor),
        subject_id=getattr(subject, 'pk', subject), object_id=object_id, outcome=outcome)
