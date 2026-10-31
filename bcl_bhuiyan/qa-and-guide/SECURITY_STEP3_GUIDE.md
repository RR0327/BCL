# Production Security Step 3: privacy, retention, backup and audit

## Scope
- `SecurityAuditEvent` records event type, timestamp, actor/subject IDs and outcome; it deliberately does not store passwords, MFA tokens, IPs or candidate answers.
- `purge_candidate_data` defaults to dry-run and only targets **completed** attempts whose `submitted_at` is older than the chosen threshold. It does not delete candidate accounts or active attempts. Because submitted_at can be null, such records are not purged automatically.
- `encrypted_backup` creates a consistent SQLite snapshot, encrypts it with Fernet and writes a SHA-256 manifest **outside the application tree**. `verify_encrypted_backup` validates checksum, decryption and SQLite integrity without changing the live database.
- PostgreSQL production backups require an independent encrypted `pg_dump` workflow and rehearsed restore.

## Required environment
Generate a key **once** with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. Store `IELTS_BACKUP_FERNET_KEY` in an external secrets manager, **never** in the repo or backup folder. Losing the key makes backups unrecoverable. Rotate only with a controlled re-encryption plan.

## Installation (PowerShell)
```
python -m pip install -r requirements.txt
python manage.py check
python manage.py migrate --plan
python manage.py migrate
python manage.py makemigrations --check --dry-run
python manage.py test bcl.test_security_step3 --verbosity 2
python manage.py test bcl --verbosity 2
```

## Regression failure collection (IMPORTANT)
The earlier run reported 134 tests, 15 failures, 2 errors. Counts alone cannot identify root causes. Run:
```
python manage.py test bcl --verbosity 2 --noinput *> regression_full.log
Select-String -Path regression_full.log -Pattern '^FAIL:','^ERROR:','^Traceback','^AssertionError','^django\.' -Context 0,12
```
Send `regression_full.log` with any subsequent fix request. Do not publish a claim that all regressions passed until this suite actually passes.

## Retention preview and execution
```
python manage.py purge_candidate_data --days 365
python manage.py purge_candidate_data --days 365 --execute --confirm DELETE-COMPLETED-ATTEMPTS
```
Perform verified backups and obtain retention-policy approval before execution. Candidate privacy requests and legal holds require separate review. Note: `PROTECT` foreign keys may prevent deletion; investigate rather than disabling integrity checks.

## Encrypted backup and non-destructive verification
```
$env:IELTS_BACKUP_FERNET_KEY = '<secret from secure vault>'
python manage.py encrypted_backup --destination D:\IELTS_secure_backups
python manage.py verify_encrypted_backup --manifest D:\IELTS_secure_backups\<generated-name>.manifest.json
```
Rehearse a restore **only into a separate, isolated environment**, validate schema and candidate records, and document RTO/RPO. For PostgreSQL, test encrypted dumps and point-in-time recovery separately.

## Production blockers still open
- Full regression suite failures must be triaged from actual tracebacks.
- MFA verification rate limiting, key management and incident-response procedures need independent review.
- Licensed complete test bank and 30 mock tests remain unverified.
- PostgreSQL encrypted backup/restore and real disaster-recovery exercise remain to be demonstrated.
- Consent notices, data subject access/erasure workflows, legal holds, retention approval and third-party privacy review remain organizational tasks.
- Browser E2E, independent penetration testing, HTTPS and private-media deployment verification remain required.
