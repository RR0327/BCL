# Production Blocker Remediation Step 4 — Release handoff

## Scope
This update preserves the Phase 3 repository and applies the two user-provided backup command files as the starting point for hardened replacements. It adds PostgreSQL archive/rehearsal tooling, read-only 30-test release gates, and repairs regression-test setup for staff MFA. It does not bypass MFA in production.

## Root causes from regression_full.log.txt
- The prior run was **140 tests: 15 failures, 3 errors** (not the earlier 134-test summary).
- 13+ staff-related failures were caused by legacy tests force-logging in staff without completing MFA. Updated tests now use a *confirmed TOTP device and session marker*; production MFA enforcement remains enabled.
- Candidate registration invoked Django `login()` without specifying an authentication backend, incompatible with multiple backends (Axes + ModelBackend). Fixed.
- Login audit test called `client.login` without a request; Axes requires a request. Test now posts to the real login view.
- Windows `WinError 32` in a SQLite backup test came from a fixture database connection not being explicitly closed. Fixed the fixture to close its handle.
- The Writing manual-evaluation assertion is rechecked through the full suite, not silenced.

## Installation and regression
Back up the current `.env`, database and media. Extract the full ZIP. Install requirements; then run:

```powershell
python -m pip install -r requirements.txt
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test bcl.test_security_step4 --verbosity 2
python manage.py test bcl --verbosity 2 --noinput 2>&1 | Tee-Object -FilePath regression_step4.log
```

## PostgreSQL backup and recovery rehearsal
Use a staging server with pg_dump/pg_restore available. Set DB_ENGINE=postgresql and valid connection settings. `--destination` must be outside the repository. The dump is **not encrypted**; secure it immediately and apply your organization's retention policy.

```powershell
python manage.py postgres_rehearsal --destination D:\IELTS_secure_backups
python manage.py postgres_rehearsal --destination D:\IELTS_secure_backups --restore-db ielts_restore_empty
python manage.py postgres_rehearsal --destination D:\IELTS_secure_backups --restore-db ielts_restore_empty --execute-restore --confirm RESTORE-ISOLATED-STAGING
```

The last command writes into the **separate existing empty staging database**. Never point it to a production database. It does not perform cleanup, overwrite, or database creation. Inspect row counts, Django migration state, authentication, and media separately. PostgreSQL backup encryption and automation remain production requirements.

## SQLite encrypted backup
Generate a Fernet key and keep it outside Git. Set `IELTS_BACKUP_FERNET_KEY` and run:

```powershell
python manage.py encrypted_backup --destination D:\IELTS_secure_backups
python manage.py verify_encrypted_backup --manifest D:\IELTS_secure_backups\YOUR_BACKUP.manifest.json
```

No plaintext backup is intentionally retained. Keep backup keys in a secrets manager and test a recovery using a disposable environment.

## Read-only test-bank and release acceptance

```powershell
python manage.py manage_testbank --audit
python manage.py release_acceptance --output release_acceptance.json
python manage.py release_acceptance --strict --output release_acceptance_strict.json
python manage.py check --deploy
```

The report requires all 30 test slots to have valid published content. It does **not** certify licensing; manually verify content provenance and permissions. Strict mode is expected to fail until all automated gates are satisfied. Manual gates (licensed test content, private media proxy, browser E2E, recovery, independent security review) must also be signed off.

## Deployment acceptance
1. Test in staging with HTTPS, real reverse proxy, private media denied by direct URL, and least-privilege database account.
2. Verify staff MFA and rate limiting; ensure recovery procedure is approved.
3. Rehearse PostgreSQL restore into isolated staging and verify data counts.
4. Confirm 30 licensed tests and Listening media play; verify exports and scoring.
5. Run all tests, check --deploy, release acceptance report, and record change-control approval.

## Release classification
**CONDITIONAL / NOT PRODUCTION APPROVED** until automated and manual gates pass. Syntax and ZIP validation are not substitutes for a passing Django suite, PostgreSQL restore rehearsal or penetration test.
