# IELTS Backend Step 6D — Test Bank Content Preflight

## Scope
Adds read-only structural content preflight, without database schema or frontend changes. Listening audio cannot be verified from JSON alone and remains an explicit manual gate; structural preflight success does not mean the test is publishable. This command **does not import or publish** content.

## Windows 11 verification
Configure a dedicated test database and activate the virtual environment, then run:

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test bcl.test_step6d_preflight --verbosity 2
python manage.py test bcl --verbosity 2
python manage.py preflight_testbank --file test1.json --output step6d_preflight.json
```

The supplied `test1.json` is incomplete; the final command should fail with actionable issues and still create a report. No database records are changed. For staging database verification, set the staging connection in environment/configuration and run `python manage.py audit_staging --require-postgres --output staging_audit_step6d.json` after confirming the connection targets `ielts_restore_empty`. Do not execute migrations or content imports on production until release approval.

## Release criteria
Licensing and editorial validation, original complete passages and questions, separately uploaded listening audio, successful browser E2E, security review, and encrypted backup/retention remain mandatory. The preflight is not a release certification.
