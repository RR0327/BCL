# Backend Step 6E — Import planning and staging safeguards

## Scope
Adds a read-only planning command. It combines the Step 6D JSON structural preflight with destination-slot protection checks. No frontend, existing source, models, or migrations changed.

## Windows 11
Activate venv, verify isolated Django test database, and run:

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test bcl.test_step6e_import_plan --verbosity 2
python manage.py test bcl --verbosity 2
```

Use staging environment configured to `ielts_restore_empty`, not the live `ielts_db`, for:

```powershell
python manage.py plan_testbank_import --file test1.json --require-postgres --output step6e_import_plan.json
python manage.py audit_staging --require-postgres --output step6e_staging_audit.json
```

The sample `test1.json` is intentionally incomplete, so the plan command should report issues and exit nonzero. Do not import or publish it. A complete authorized payload may be eligible for import into an empty unpublished slot, but this command never imports anything. Upload listening audio via admin after import and verify the actual media and candidate workflows before publishing. PostgreSQL data and secrets are not bundled in the repository.
