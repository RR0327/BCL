# IELTS Backend Step 6L — PostgreSQL cross-endpoint concurrency

## Scope
Adds four real-transaction PostgreSQL tests for answer/submit, concurrent answer upserts, violation/submit, and expiry/submit races. No production code, schema, frontend, or URL changes.

## Windows 11
Extract the full project ZIP into a separate directory. Activate the existing virtual environment and configure a **disposable PostgreSQL test database**. Do not run tests against the production or staging database.

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test bcl.test_step6l_postgres_races --verbosity 2
python manage.py test bcl --verbosity 2
```

Confirm the four new tests run without skips. For isolated staging `ielts_restore_empty`, run only read-only audits:

```powershell
python manage.py audit_candidate_workflows --require-postgres --output step6l_candidate_audit.json
python manage.py audit_staging --require-postgres --output step6l_staging_audit.json
```

## Acceptance
- Four new PostgreSQL tests pass without skips.
- Full Django regression suite passes.
- No unexpected migrations.
- Both read-only staging audits complete and anomalies are reviewed.
- Frontend, routes, scoring and prior behavior are unchanged.

## Limitations
Concurrency tests validate the exercised races; they do not prove all interleavings or certify production readiness. Exam content, audio, writing review, browser end-to-end, and release security controls remain outstanding.
