# Backend Step 6J — Expiry transaction lock-order hardening

## Purpose
Align the lazy expiration path used by timer/session/rules/result with the candidate-first lock order already used by start/save/violation/submit endpoints. PostgreSQL row locks serialize these operations for the same candidate, reducing deadlock risk and expiry/write races. No schema or frontend changes.

## Complete replacement and new files
- `bcl/exam_views.py` — full replacement; `expire_attempt_if_needed()` now locks the candidate row before locking the attempt row.
- `bcl/test_step6j_expiry_integrity.py` — six new tests, including idempotent expiry, scoring-once, ownership, and read-path expiration.

## Windows 11 verification
Run from the Django project directory with your virtual environment activated:

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test bcl.test_step6j_expiry_integrity --verbosity 2
python manage.py test bcl --verbosity 2
```

For isolated PostgreSQL staging (verify the database name is `ielts_restore_empty` first):

```powershell
python manage.py audit_candidate_workflows --require-postgres --output step6j_candidate_audit.json
python manage.py audit_staging --require-postgres --output step6j_staging_audit.json
```

Do not point destructive tests at the live database. The audit commands are read-only. Database-level race guarantees require PostgreSQL integration tests and are not established by SQLite tests. Verify the entire candidate browser flow separately.

## Acceptance
1. Django system check passes.
2. No migration drift.
3. Six new Step 6J tests pass.
4. Full `bcl` suite passes.
5. Both staging audits run on isolated PostgreSQL.
6. Frontend and existing flows remain functional.
