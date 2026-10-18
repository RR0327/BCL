# Phase 5 Step 4 — Release and Handoff Runbook

## Release decision
**Status: CONDITIONAL / NOT APPROVED FOR PUBLIC PRODUCTION.** Passing Django tests is necessary but not sufficient.
This package contains the complete inherited repository for continuity, including the development database and audio files. **Do not publish the full ZIP** to a public repository or deploy it as-is.

## Production blockers
1. Uploaded exam media is served from a conventional media directory. Implement authenticated, attempt-scoped media delivery or signed URLs and verify direct URL denial. Browser-hidden audio controls do not provide DRM.
2. No independent penetration test, vulnerability scan, or verified browser E2E suite has been supplied.
3. Thirty initialized test slots are not equivalent to 30 licensed, populated, quality-reviewed exams. Client-owned content, licensing and readiness review remain mandatory.
4. PostgreSQL data migration from SQLite, staging rehearsals, rollback and restore drills must be verified. Django `migrate` does not move SQLite records.
5. Set production domain, trusted origins, HTTPS, secrets, SMTP/notification configuration, retention policy, staff MFA and rate limiting before launch.
6. Confirm candidate personal data consent, backup encryption, retention/deletion procedures and restricted examiner access.
7. Ensure migration source files are tracked by Git. The inherited `.gitignore` excludes migration Python files; this release corrects that rule.

## Developer checks (Windows PowerShell)
From `sakib-bhai/bcl_bhuiyan` with activated virtual environment:

```powershell
python -m pip install -r requirements.txt
python manage.py check
python manage.py makemigrations bcl --check --dry-run
python manage.py test bcl --verbosity 2
python manage.py manage_testbank --audit
python manage.py release_check --output release_preflight_local.json
python manage.py backup_sqlite --destination D:\IELTS_secure_backups
```

The local preflight is intentionally non-strict; it does **not** mean production approval.
`backup_sqlite` requires a SQLite configuration and writes a consistent backup and SHA-256 manifest to a directory outside the project. Protect this directory using OS access controls and encryption.

## Production staging gate
Configure environment variables from `.env.example` using separate production secrets and a PostgreSQL database.
With `DJANGO_DEBUG=False` and HTTPS reverse proxy configured:

```powershell
python manage.py check --deploy
python manage.py migrate --plan
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py release_check --strict --output release_preflight_staging.json
```

Strict preflight deliberately fails the media-access review gate until the control is implemented and manually audited; do not bypass it merely to turn the result green.

## PostgreSQL backup and recovery
Run PostgreSQL backups using `pg_dump --format=custom --file=... DB_NAME` with credentials passed securely through the deployment environment, not shell history. Use `pg_restore --list` to inspect backups and rehearse restoration into an isolated staging database. Never restore into the live database without a signed-off recovery plan. Use encryption at rest and offsite retention.

## SQLite recovery rehearsal
1. Stop write traffic on an isolated staging copy.
2. Confirm SHA-256 of the backup matches the JSON manifest.
3. Restore a copy of the `.sqlite3` backup to a **separate** staging location.
4. Execute `PRAGMA integrity_check`, Django checks and application smoke tests.
5. Record the recovery time, backup timestamp and operator approval.

## Release acceptance
Record the commit hash, dependency lock or resolved versions, Python version, DB version, deployment target, successful test outputs, QA sign-off, privacy sign-off and verified restore drill. Only then approve a controlled rollout with monitoring and rollback ownership.

## Candidate smoke tests
Candidate login/logout; attempt ownership; Reading highlights and answers; Listening audio start/refresh behavior; Writing autosave and word counts; timer expiry; second focus-loss auto-submit; result access; staff-only Writing evaluation; PDF/DOCX exports; test-bank audit; unauthorized media URL checks.

## Rollback
Maintain immutable application release and separate database backups. Roll back code only when schema compatibility is confirmed. Database rollback must follow an approved restoration plan; reverse migrations can destroy data.
