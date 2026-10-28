# Device Switch and Release Handoff

This document records the current project state and the safe process for continuing
work on another Windows device.

## 1. Project location

The Django project root is the directory containing `manage.py`:

```text
G:\Shaikat\BCL-Bhuiyan\bcl_bhuiyan
```

On the new device, use the equivalent local path and run all Django commands from
that directory.

## 2. Work completed

- Reading supports multiple passages/sections and grouped questions.
- Fill-in-the-blank questions support multiple numbered blanks and answer
  alternatives.
- Matching and Matching Information question types are supported.
- Option keys are required, while option text may be blank.
- Passage and per-question instructions are supported.
- Reading uses a split passage/question layout with navigation and highlighting.
- Candidate session hardening was added across Steps 6G through 6I.
- PostgreSQL concurrency checks were added in Step 6K.
- PostgreSQL cross-endpoint race checks were added in Step 6L.
- Exam asset audit checks were added in Step 6M.
- No new migration is required for the Step 6K connection-cleanup change.

## 3. Never copy secrets into documentation

Do not copy passwords, Django secret keys, encryption keys, or the complete
`.env` file to the new device through chat, Git, or this document.

Create a private `.env` file on the new device from `.env.example`, then enter
the values using your secret manager or another secure transfer method.

If a secret has been exposed, rotate it before using the new device.

## 4. New-device setup

Install:

- Git
- Python 3.13 or the project-supported Python version
- PostgreSQL client/server as required
- PostgreSQL command-line tools available on `PATH`
- A virtual environment

Clone or copy the repository, then enter the project directory:

```powershell
cd G:\Shaikat\BCL-Bhuiyan\bcl_bhuiyan
```

Create and activate a virtual environment:

```powershell
py -3.13 -m venv ..\venv
.\..\venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Create the local environment file:

```powershell
Copy-Item .env.example .env
```

Edit `.env` privately. At minimum, configure a valid `DJANGO_SECRET_KEY`,
`DJANGO_ALLOWED_HOSTS`, and the intended database settings.

## 5. Database roles

Use these database roles carefully:

| Database | Purpose | Safe to modify? |
|---|---|---|
| `ielts_db` | PostgreSQL source/application database | Only during an approved deployment |
| `ielts_restore_empty` | Existing restore rehearsal target | Preserve restore evidence; do not reuse |
| `ielts_restore_verify_20261021` | Existing restore verification copy | Preserve as evidence |
| `ielts_content_staging` | Recommended isolated database for content work | Yes, staging only |
| `ielts_test_*` | Temporary Django test database | Disposable only |

Never run destructive test cleanup against `ielts_db` or either restored evidence
database.

## 6. Select a database for Django

Set the variables in the same PowerShell window used for Django commands.

### Local SQLite development

```powershell
$env:DB_ENGINE="sqlite3"
$env:DB_NAME="db.sqlite3"
$env:DJANGO_DEBUG="True"
$env:DJANGO_SECURE_SSL_REDIRECT="False"
$env:TRUST_PROXY_SSL_HEADER="False"
$env:DJANGO_ALLOWED_HOSTS="127.0.0.1,localhost"
```

Start local HTTP development:

```powershell
python manage.py runserver 127.0.0.1:8000
```

Open:

```text
http://127.0.0.1:8000/
```

### PostgreSQL staging

Use the real password privately; never use the placeholder literally:

```powershell
$env:DB_ENGINE="postgresql"
$env:DB_NAME="ielts_restore_verify_20261021"
$env:DB_USER="ielts_app"
$env:DB_PASSWORD="YOUR_REAL_PASSWORD"
$env:DB_HOST="127.0.0.1"
$env:DB_PORT="5432"
$env:DB_SSLMODE="prefer"
```

For content work, use an independently provisioned staging database instead:

```powershell
$env:DB_NAME="ielts_content_staging"
```

### Production-equivalent staging controls

Only use these on HTTPS-enabled staging:

```powershell
$env:DJANGO_DEBUG="False"
$env:DJANGO_SECURE_SSL_REDIRECT="True"
$env:DJANGO_ALLOWED_HOSTS="your-real-staging-hostname"
```

Do not enable proxy trust until the reverse proxy overwrites
`X-Forwarded-Proto` correctly.

## 7. Confirm the active database before every sensitive command

Run:

```powershell
python manage.py shell -c "from django.conf import settings; print('ENGINE=', settings.DATABASES['default']['ENGINE']); print('NAME=', settings.DATABASES['default']['NAME'])"
```

For restored staging, expected output includes:

```text
ENGINE= django.db.backends.postgresql
NAME= ielts_restore_verify_20261021
```

Also verify directly with PostgreSQL:

```powershell
psql -h 127.0.0.1 -p 5432 -U ielts_app -d ielts_restore_verify_20261021 -c "SELECT current_database(), current_user;"
```

Do not continue if the database name is not the intended isolated target.

## 8. Migration and system checks

Run:

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate --check
```

`makemigrations --check --dry-run` should report:

```text
No changes detected
```

Apply migrations only to an intentionally selected staging database:

```powershell
python manage.py migrate
```

Do not run `migrate` against a production database without an approved backup and
deployment procedure.

## 9. PostgreSQL restore verification

The restore target must be a separate, empty database. Do not run migrations
against it before restoring a dump.

The successful restore evidence previously produced was:

```text
PostgreSQL dump and archive inspection passed
Staging restore command succeeded; verify data and application separately.
```

After restoration, verify the target:

```powershell
psql -h 127.0.0.1 -p 5432 -U ielts_app -d ielts_restore_verify_20261021 -c "SELECT current_database(), current_user;"
psql -h 127.0.0.1 -p 5432 -U ielts_app -d ielts_restore_verify_20261021 -c "SELECT COUNT(*) AS tests FROM bcl_ieltsmocktest;"
```

The previous verification found 30 mock-test rows. This does not prove that the
tests are complete or ready for release.

## 10. Test-bank workflow

Audit the selected staging database:

```powershell
python manage.py manage_testbank --audit
```

Import only authorized, complete JSON content:

```powershell
python manage.py manage_testbank --import-json "C:\secure\authorized_test.json" --dry-run
python manage.py manage_testbank --import-json "C:\secure\authorized_test.json"
```

The repository's `testbank_json\test1.json` is an incomplete demonstration
fixture. It must not be published and cannot satisfy release acceptance.

## 11. Regression tests

Use a disposable PostgreSQL test database name so stale test databases do not
interfere with a new run:

```powershell
$env:DB_TEST_NAME="ielts_test_step6k_newdevice"
python manage.py test bcl.test_step6k_postgres_concurrency --verbosity 2
Remove-Item Env:DB_TEST_NAME -ErrorAction SilentlyContinue
```

For Step 6L:

```powershell
$env:DB_TEST_NAME="ielts_test_step6l_newdevice"
python manage.py test bcl.test_step6l_postgres_races --verbosity 2
Remove-Item Env:DB_TEST_NAME -ErrorAction SilentlyContinue
```

The expected result must include both:

```text
Ran N tests
OK
Destroying test database for alias 'default'...
```

If tests pass but teardown reports that the database is being accessed by other
users, the test result is not fully clean. Terminate connections and remove only
the disposable test database:

```powershell
$env:PGPASSWORD = Read-Host "PostgreSQL administrator password"
psql -h 127.0.0.1 -p 5432 -U postgres -d postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'ielts_test_step6l_newdevice' AND pid <> pg_backend_pid();"
psql -h 127.0.0.1 -p 5432 -U postgres -d postgres -c "DROP DATABASE IF EXISTS ielts_test_step6l_newdevice;"
Remove-Item Env:PGPASSWORD
```

Replace the database name with the exact disposable name used.

## 12. Step 6M storage-test note

Storage existence tests must patch the storage instance or the concrete storage
backend class, not the `DefaultStorage` class itself:

```python
patch.object(type(self.section.audio_file.storage), "exists", return_value=False)
```

Do not use `patch.object(DefaultStorage, "exists", ...)` when the error says that
`DefaultStorage` has no attribute `exists`.

## 13. Audits against isolated staging

After confirming the active database is the isolated PostgreSQL staging database:

```powershell
python manage.py audit_candidate_workflows --require-postgres --output candidate_workflow_audit.json
python manage.py audit_staging --require-postgres --output staging_audit.json
```

Review both JSON files. A generated report is not automatically a passing report.
Investigate every finding.

## 14. Final acceptance

Run:

```powershell
python manage.py check --deploy
python manage.py test bcl --verbosity 2
python manage.py release_acceptance --strict --output release_acceptance_strict_final.json
```

Acceptance is not complete unless:

- The full test command ends with `OK` and no teardown traceback.
- No unexpected migrations are detected.
- The strict report contains `"automated_gates_pass": true`.
- All licensed test content is complete and published.
- Browser workflows, MFA, private media, backup/restore, monitoring, security
  review, and rollback are separately verified.

## 15. Safe troubleshooting rules

- Confirm the active database before `migrate`, imports, audits, or content edits.
- Never run Django tests against `ielts_db` or a restore-evidence database.
- Never delete a database unless its name is a disposable test/staging target and
  the target has been independently confirmed.
- Do not paste passwords, `.env` files, secret keys, or encryption keys into chat.
- Keep the original repository and restore evidence unchanged while working on a
  new device.

## 16. Database data transfer to the new device

Transfer database data using a backup artifact. Do not copy a live PostgreSQL data
directory and do not copy a database while it is being written.

### PostgreSQL transfer

On the old device, create a custom-format dump from the approved source database.
The destination must be outside the repository:

```powershell
$env:PGPASSWORD = Read-Host "Source PostgreSQL password"
& "C:\Program Files\PostgreSQL\18\bin\pg_dump.exe" `
  -h 127.0.0.1 `
  -p 5432 `
  -U ielts_app `
  -d ielts_db `
  --format=custom `
  --file "D:\IELTS_secure_backups\ielts-transfer-YYYYMMDD.dump"
Remove-Item Env:PGPASSWORD
```

Verify that the dump exists and has a non-zero size:

```powershell
Get-Item "D:\IELTS_secure_backups\ielts-transfer-YYYYMMDD.dump"
& "C:\Program Files\PostgreSQL\18\bin\pg_restore.exe" `
  --list "D:\IELTS_secure_backups\ielts-transfer-YYYYMMDD.dump"
```

Transfer the dump to the new device only through an approved private channel.
Encrypt it before transfer or storage if the organization requires encrypted
backups. Do not send it through chat or commit it to Git.

On the new device, create a separate empty staging database. Use a PostgreSQL
administrator account only for provisioning the target:

```powershell
$env:PGPASSWORD = Read-Host "PostgreSQL administrator password"
psql -h 127.0.0.1 -p 5432 -U postgres -d postgres -c "CREATE DATABASE ielts_content_staging OWNER ielts_app;"
Remove-Item Env:PGPASSWORD
```

Restore the dump into that empty staging database. Do not run `migrate` before
restoring a dump that already contains the schema:

```powershell
$env:PGPASSWORD = Read-Host "Application PostgreSQL password"
& "C:\Program Files\PostgreSQL\18\bin\pg_restore.exe" `
  -h 127.0.0.1 `
  -p 5432 `
  -U ielts_app `
  -d ielts_content_staging `
  --exit-on-error `
  --single-transaction `
  --verbose `
  "D:\IELTS_secure_backups\ielts-transfer-YYYYMMDD.dump"
Remove-Item Env:PGPASSWORD
```

The target must be empty. If `pg_restore` reports that a relation already exists,
stop and use a new empty staging database. Do not add `--clean` or restore into
`ielts_db`.

### PostgreSQL transfer verification

Configure Django for the transferred staging database:

```powershell
$env:DB_ENGINE="postgresql"
$env:DB_NAME="ielts_content_staging"
$env:DB_USER="ielts_app"
$env:DB_PASSWORD="YOUR_REAL_PASSWORD"
$env:DB_HOST="127.0.0.1"
$env:DB_PORT="5432"
$env:DB_SSLMODE="prefer"
```

Confirm the database identity:

```powershell
python manage.py shell -c "from django.conf import settings; print(settings.DATABASES['default']['ENGINE']); print(settings.DATABASES['default']['NAME'])"
psql -h 127.0.0.1 -p 5432 -U ielts_app -d ielts_content_staging -c "SELECT current_database(), current_user;"
```

Compare source and target counts without exposing row contents:

```powershell
psql -h 127.0.0.1 -p 5432 -U ielts_app -d ielts_db -c "SELECT (SELECT COUNT(*) FROM auth_user) AS users, (SELECT COUNT(*) FROM bcl_ieltsmocktest) AS tests, (SELECT COUNT(*) FROM bcl_exammodule) AS modules, (SELECT COUNT(*) FROM bcl_examsection) AS sections, (SELECT COUNT(*) FROM bcl_question) AS questions, (SELECT COUNT(*) FROM bcl_questionoption) AS options;"
psql -h 127.0.0.1 -p 5432 -U ielts_app -d ielts_content_staging -c "SELECT (SELECT COUNT(*) FROM auth_user) AS users, (SELECT COUNT(*) FROM bcl_ieltsmocktest) AS tests, (SELECT COUNT(*) FROM bcl_exammodule) AS modules, (SELECT COUNT(*) FROM bcl_examsection) AS sections, (SELECT COUNT(*) FROM bcl_question) AS questions, (SELECT COUNT(*) FROM bcl_questionoption) AS options;"
```

Record the dump filename, dump timestamp, source counts, target counts, migration
status, and any intentional differences. A matching test count alone does not
prove that all content or media was transferred.

### SQLite transfer

For local SQLite development only, stop Django first and copy the SQLite file
while no process is writing to it:

```powershell
Copy-Item "G:\Shaikat\BCL-Bhuiyan\bcl_bhuiyan\db.sqlite3" `
  "D:\IELTS_secure_backups\db.sqlite3"
```

On the new device, place the copy at the configured `DB_NAME` path and verify:

```powershell
$env:DB_ENGINE="sqlite3"
$env:DB_NAME="db.sqlite3"
python manage.py check
python manage.py migrate --check
```

SQLite transfer is not a substitute for a PostgreSQL production backup or restore.
For production-equivalent staging, use the PostgreSQL custom-format dump process
above.

### Media transfer

Database dumps do not include files stored under `MEDIA_ROOT`. Transfer private
media separately through an approved secure channel, preserve file permissions,
and verify the media paths referenced by the database. Run:

```powershell
python manage.py audit_exam_assets --require-postgres --output exam_assets_audit.json
```

Review the report before candidate testing. Never make private media publicly
readable just to make an asset check pass.
