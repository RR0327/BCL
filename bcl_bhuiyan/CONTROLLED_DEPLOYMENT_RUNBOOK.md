# Controlled Deployment and Post-Launch Operations — 2026-10-20

## Decision
**NO-GO for public production.** The regression suite passes (144/144), but strict acceptance fails, PostgreSQL restoration was not executed, and 0/30 test slots are ready. A controlled **non-public staging deployment** is appropriate for validation; do not onboard real candidates or publicly expose examination media.

## Preserve the release
1. Keep the original final repository ZIP immutable; record SHA-256 and archive it in access-controlled storage.
2. Back up the existing SQLite database and media files separately, and verify backups before migration. The inherited repository ZIP contains a SQLite database and media; **do not publish this archive to a public Git repository** without sanitizing sensitive data and licensed media.
3. Keep `.env`, Fernet keys, PostgreSQL passwords, MFA recovery material, and any dump files out of source control.
4. Deploy a versioned release with a documented rollback target and named release owner.

## Stage 1 — PostgreSQL provisioning (DBA-controlled)
Provision separate source and empty restore databases, with distinct credentials and minimum required privileges. Verify connectivity and database identity using `psql` before running Django commands. Configure `.env` with `DB_ENGINE=postgresql`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, and `DB_SSLMODE` according to the actual settings and TLS environment. Never point a restore command at the live production database.

**Important:** Changing the configured database does not migrate SQLite data automatically. Plan and rehearse data migration separately; take a source snapshot, import to staging, reconcile row counts, validate foreign keys and attachments, and test the application.

## Stage 2 — isolated backup and recovery rehearsal
1. Validate PostgreSQL client binaries and server version compatibility.
2. Confirm that the restore target is a dedicated empty staging database and that the account cannot write to the production database.
3. Execute `python manage.py postgres_rehearsal --destination D:\IELTS_secure_backups` against the **verified PostgreSQL source**.
4. Review command help and guide before executing the destructive restore option; use only the explicitly confirmed staging target.
5. Capture `pg_dump` and `pg_restore` exit codes, dump checksums, restored table/row counts, migration state, and Django smoke-test results.
6. Encrypt backup artifacts, restrict permissions, record offsite retention, and test restoration from the retained encrypted copy.
7. Document RPO/RTO targets and measure actual recovery time.

## Stage 3 — production-equivalent staging security
- `DEBUG=False`, explicit `ALLOWED_HOSTS`, HTTPS termination, correct proxy trust, `SECURE_SSL_REDIRECT=True`, secure session and CSRF cookies, and HSTS only after HTTPS is proven.
- Verify Django `check --deploy` and `release_acceptance --strict` in the **staging configuration**. A local SQLite report is not evidence of production readiness.
- Deny direct `/media/` access at web server, CDN and object storage. Test authenticated, attempt-scoped streaming and expiry.
- Verify staff MFA, TOTP verification rate limiting, login throttling behind the real proxy, staff recovery procedure, CSRF, session expiration and logout.
- Complete vulnerability scanning, dependency review, privacy/retention approval and authorized browser E2E testing.

## Stage 4 — content acceptance
- Initialize/import all 30 licensed IELTS mock tests. Confirm Reading 3 sections/40 questions, Listening 4 sections/40 questions and audio, and Writing 2 tasks per test as required by the test bank guide.
- Verify answers, media permissions, editorial quality, accessibility, and documented content rights.
- Run `python manage.py manage_testbank --audit` and `python manage.py release_acceptance --strict --output release_acceptance_staging.json`.

## Controlled release / rollback
Only after all gates pass: deploy to a restricted canary cohort; confirm login, registration, Listening audio, Reading/ Writing, autosave, exam timers, submission, grading, staff review, exports, and recovery. Snapshot data before schema changes. On incident, disable new sessions, preserve logs, roll back application release where schema-compatible, and restore database only under an approved data-loss plan. Never blindly restore an old backup over live submissions.

## Monitoring and alerting
- Availability: external HTTPS synthetic checks every 5 minutes; alert on repeated failures.
- Application: 5xx rate, request latency, error exceptions, task failures, and failed media authorization spikes.
- Authentication: login lockouts, staff MFA failures, suspicious repeated attempts; never log passwords or TOTP secrets.
- Examination: autosave error rate, timer discrepancies, abnormal forced submissions, audio delivery errors, incomplete scoring.
- Database: connection failures, storage growth, slow queries, migration drift, backup freshness and restore-rehearsal date.
- Backups: alert if scheduled backup/verification fails; conduct periodic isolated restore rehearsals.
- Privacy: retention job dry-run summaries, deletion approvals, audit-log integrity and access review.
- Set actual thresholds after a baseline period; page the on-call owner for security incidents, data loss, or sustained outage.

## Launch-day operational cadence
T-24h: final signoff and verified backups. T-2h: migration plan and rollback review. T0: limited canary. T+15m and T+1h: review error, auth, media, and autosave dashboards. T+24h: first-day incident review. First week: daily review and backup checks. First month: weekly release/security review and one isolated restore rehearsal.

## Evidence required for GO
1. A passing PostgreSQL staging restore transcript with reconciliation and smoke tests.
2. A passing strict release acceptance JSON from the production-equivalent staging environment.
3. 30/30 complete licensed tests, or an explicitly approved reduced-scope release with corresponding acceptance criteria.
4. Passing 144-test regression (provided) plus production browser E2E and independent security assessment.
5. Signed approval by engineering, security, content owner and operations.
