# IELTS Backend Step 6C — PostgreSQL staging audit

## Scope
Adds a **read-only** `audit_staging` command and seven regression tests. Does not modify models, migrations, frontend, or stored test-bank content. Does not declare release readiness. Source repository is the verified Step 6B quality regression fix archive.

## Replacement and new files
- NEW `bcl/management/commands/audit_staging.py` — aggregate-only database and readiness audit.
- NEW `bcl/test_step6c_staging.py` — seven automated tests.
- NEW `BACKEND_STEP6C_STAGING_GUIDE.md` — this guide.
- No existing Python source files replaced.

## Windows 11 instructions
1. Extract into a NEW folder and restore your own private `.env` configuration. The ZIP intentionally excludes secrets and database snapshots.
2. Activate your virtual environment and install `requirements.txt` if needed.
3. Confirm the active database is the isolated staging PostgreSQL database, **not** the live source database. Use separate credentials and settings.
4. Run:

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test bcl.test_step6c_staging --verbosity 2
python manage.py test bcl --verbosity 2
python manage.py audit_staging --require-postgres --output "staging_audit_step6c.json"
```

Expected: system checks pass, no new migrations, seven new tests pass, full suite passes, audit prints JSON counts. With the user's prior staging data, expect 30 mock-test slots, 2 users, zero questions and zero ready tests **if the database has not changed**.

Optionally use `--strict` to fail on missing slots or incomplete **published** tests. Strict does **not** require all 30 tests to be populated; it is a database consistency gate, **not** a production release gate.

## Safety and limitations
- Never use the same database for staging and production.
- Django's test runner uses a separate test database; verify test database isolation and privileges before execution.
- Report has aggregate counts only; keep even aggregate operational reports internal.
- No actual PostgreSQL staging connection or full Django suite was run in the authoring environment; validate on Windows.
- Missing authorized IELTS passages, audio and essay prompts still block content readiness.
