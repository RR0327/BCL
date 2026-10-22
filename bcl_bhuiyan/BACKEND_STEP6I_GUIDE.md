# IELTS Backend Step 6I — Candidate read-side session integrity

Baseline: Step 6H. No database migrations or frontend edits.

## Changes
- Older duplicate active attempts redirect away from the examination page to the existing rules/start flow.
- Timer polling for an older duplicate active attempt returns HTTP 409 with `status=superseded` and `remaining_seconds=0`.
- Existing write protections, candidate ownership checks, expiration scoring and session routes are preserved.
- Seven tests cover old/new session access, timer conflicts, candidate isolation, expiration and closed attempts.

## Windows verification (PowerShell)
From the project root with the virtual environment activated:

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test bcl.test_step6i_read_integrity --verbosity 2
python manage.py test bcl --verbosity 2
```

Confirm the configured database is the isolated staging database `ielts_restore_empty` **before** running these read-only commands:

```powershell
python manage.py audit_candidate_workflows --require-postgres --output step6i_candidate_audit.json
python manage.py audit_staging --require-postgres --output step6i_staging_audit.json
```

## Limitations
The CI/test suite has not been executed in the packaging environment. Browser E2E, real PostgreSQL concurrency and full examination content/media verification remain required. Never import or publish incomplete/unlicensed content.
