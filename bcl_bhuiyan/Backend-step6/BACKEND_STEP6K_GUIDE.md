# IELTS Backend Step 6K — PostgreSQL concurrency verification

Baseline: IELTS_Backend_Step6J_Full_Project.zip. This step adds a PostgreSQL-specific real-transaction test suite. No existing source, frontend, migrations, or routes are changed.

## New complete file

- `bcl/test_step6k_postgres_concurrency.py`: three `TransactionTestCase` tests. They use independent connections in two threads to verify (1) simultaneous starts create/reuse one session, (2) simultaneous submissions close one session, and (3) simultaneous starts repair legacy duplicate active attempts. These tests skip on non-PostgreSQL databases.

## Windows 11 instructions

1. Extract the project ZIP to a new directory. Restore your own private `.env` locally; it is intentionally not included in the archive.
2. Activate your virtual environment and configure a dedicated PostgreSQL TEST database. Ensure Django's `TEST.NAME` is an isolated disposable database such as `ielts_test`; do **not** point test operations at `ielts_db` or `ielts_restore_empty`.
3. Run:

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test bcl.test_step6k_postgres_concurrency --verbosity 2
python manage.py test bcl --verbosity 2
```

Expected: three Step 6K tests pass **on PostgreSQL**, with no skipped Step 6K tests. If skipped, check DATABASES ENGINE; the concurrency acceptance gate is not satisfied.

4. For read-only staging audits only, confirm connection to `ielts_restore_empty` then run:

```powershell
python manage.py audit_candidate_workflows --require-postgres --output step6k_candidate_audit.json
python manage.py audit_staging --require-postgres --output step6k_staging_audit.json
```

## Limitations

- These tests verify application-level serialization for the tested endpoints, not every possible direct database writer.
- No real PostgreSQL tests were executed during package creation; run them in your own isolated environment.
- Production release still requires licensed test content, Listening audio, Writing assessment, browser E2E, security review and backup/restore verification.
