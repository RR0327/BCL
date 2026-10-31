# Phase 5 Step 3 — Security and deployment handoff

## Scope and validation boundary
The project supports SQLite development and opt-in PostgreSQL production configuration. The existing local database and media are preserved in the complete ZIP. This is **not** evidence that PostgreSQL migration, penetration testing, real-browser E2E testing, or a public deployment has succeeded.

## 1. Local verification (PowerShell)
```powershell
cd bcl_bhuiyan
python -m pip install -r requirements.txt
# Keep your existing .env, or copy .env.example and set a secure DJANGO_SECRET_KEY
python manage.py check
python manage.py makemigrations bcl --check --dry-run
python manage.py test bcl.test_phase5_security --verbosity 2
python manage.py test bcl --verbosity 2
python manage.py manage_testbank --audit
python manage.py runserver
```

## 2. Production preparation
1. Provision PostgreSQL with separate least-privilege credentials, TLS and backups. Test a database restore.
2. Set `DJANGO_DEBUG=False`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_SECRET_KEY`, `DJANGO_CSRF_TRUSTED_ORIGINS`, `DB_ENGINE=postgresql`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `DB_SSLMODE=require` in a secret manager. Do not publish these values.
3. Configure TLS termination at a trusted reverse proxy. Only set `TRUST_PROXY_SSL_HEADER=True` if the proxy strips incoming `X-Forwarded-Proto` and sets its own. Otherwise leave False.
4. Back up the SQLite database and media before migrating. `migrate` on PostgreSQL creates schema; **it does not copy existing SQLite records**. Plan and test a separate data migration, accounting for primary keys and sequence resets.
5. Run `python manage.py check --deploy`, `python manage.py migrate --plan`, `python manage.py migrate`, `python manage.py collectstatic --noinput`, then `python manage.py check --deploy` again. Investigate warnings rather than blindly suppressing them.
6. Set `DJANGO_HSTS_SECONDS` to a positive value only after confirming HTTPS for the entire site and subdomains; never preload without explicit approval.
7. Run a supported WSGI server behind the proxy (for example `waitress-serve --listen=127.0.0.1:8000 bcl_bhuiyan.wsgi:application` on Windows). Do not use `runserver` publicly.
8. **Do not expose `/media/` publicly.** Uploaded Listening audio and exam content need authenticated, authorization-checked delivery or private object storage with short-lived access. The current exam interface may rely on direct media URLs; this is an unresolved production blocker.
9. Restrict staff/admin accounts, rotate credentials, enforce MFA at the identity/proxy layer, configure rate limiting, audit logs and encrypted off-site backups. Django alone does not supply all these controls.
10. Test a production-like environment: full candidate workflows, exports, file uploads, browser audio interruption, proxy headers, HTTPS redirects, CSRF, and restoration from backup.

## 3. Release blockers
- Client-authorized content must be ingested and audited before publishing all 30 tests.
- Direct media access and audio manipulation are not fully protected; browser restrictions cannot guarantee unpausable audio.
- A production-grade security assessment, upload validation review and performance/load tests remain necessary.
- PostgreSQL data migration and restoration have not been executed by this package.
- The inherited `.gitignore` excludes migration source files; change this rule only after repository policy approval, and explicitly track migrations for releases.

## 4. Rollback
Back up `.env`, DB, uploaded media and release ZIP. Stop traffic; restore the previous application version and its compatible DB backup. Do not assume a database migration can be reversed without data loss.
