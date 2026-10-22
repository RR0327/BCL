# IELTS Backend Step 6H — Candidate session write integrity

## Scope

The exam answer-save, violation-report, and submit endpoints now acquire a candidate-level transaction lock before locking an attempt, matching the lock ordering of `start_exam`. They reject state-changing requests against older duplicate active attempts with HTTP 409. The newest active attempt remains writable. The existing start endpoint performs cleanup and scoring of legacy duplicates.

No migrations or frontend changes. The check is not a substitute for a database-level uniqueness constraint; follow-up production hardening should consider a partial unique constraint after cleaning historical duplicates and evaluating concurrency across all code paths.

## Windows PowerShell verification

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test bcl.test_step6h_integrity --verbosity 2
python manage.py test bcl --verbosity 2
```

Verify the isolated staging PostgreSQL database is selected before running read-only audits:

```powershell
python manage.py audit_candidate_workflows --require-postgres --output step6h_candidate_audit.json
python manage.py audit_staging --require-postgres --output step6h_staging_audit.json
```

Never run destructive database commands on production. This package excludes `.env` and local database artifacts. Restore local environment settings from your secure backup.

## Expected results

Six Step 6H regression tests pass, full existing suite passes, Django check succeeds, no new migrations, and JSON staging audit reports are generated. Investigate any audit anomalies. Actual tests must be executed in your environment; archive and syntax checks alone do not establish integration success.
