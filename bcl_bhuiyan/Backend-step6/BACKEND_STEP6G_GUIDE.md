# Backend Step 6G — Candidate session hardening

## Changes
- On exam start, lock the candidate row and retain the newest unexpired in-progress attempt.
- Automatically submit and score expired or duplicate older in-progress attempts.
- Add six regression tests for duplicate-session cleanup, expiration, ownership, publication and answer rejection.
- No migrations, frontend changes or changes to existing URL contracts.

## Safety
The duplicate remediation occurs only when the candidate explicitly starts the same module. The integrity audit remains read-only. It is not a bulk staging-data repair and does not guarantee that historical duplicates elsewhere have been remediated. PostgreSQL row locking serializes exam-start requests for the same candidate, but direct database writes or other application paths may still create duplicates.

## Windows verification
Use an isolated PostgreSQL test database and never run destructive tests against the restored staging database.

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test bcl.test_step6g_hardening --verbosity 2
python manage.py test bcl --verbosity 2
python manage.py audit_candidate_workflows --require-postgres --output step6g_workflow_audit.json
python manage.py audit_staging --require-postgres --output step6g_staging_audit.json
```

Configure the last two read-only commands for the isolated staging database `ielts_restore_empty`. Verify output files exist and review any anomalies. If anomalies are present, investigate before release.

## Remaining release blockers
Complete authorized examination content, Listening audio playback, examiner rubric, real candidate browser E2E, staging restore validation and independent security review.
