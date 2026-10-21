# Backend Step 6F — Candidate workflow integrity and PostgreSQL staging

## Scope
Read-only candidate workflow audit, eight automated regression tests, and candidate start/save/submit/scoring/ownership checks. No existing frontend or source file changed. No migrations.

## Windows PowerShell

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test bcl.test_step6f_workflow_audit --verbosity 2
python manage.py test bcl --verbosity 2
```

Confirm your configured database is the **isolated** `ielts_restore_empty` PostgreSQL staging database (not production). Then run:

```powershell
python manage.py audit_staging --require-postgres --output step6f_staging_audit.json
python manage.py audit_candidate_workflows --require-postgres --output step6f_candidate_workflow_audit.json
```

`passed: true` means only the defined aggregate consistency checks passed, not full production acceptance. To fail CI on anomalies, add `--fail-on-anomaly`. An expired in-progress attempt is reported rather than modified. Never run database-mutating test commands against production.

## Release blockers
Examination licensing, full 40-question Reading and Listening content, audio playback, Writing rubrics, full browser E2E, staging restore validation, and security approval remain separate gates.
