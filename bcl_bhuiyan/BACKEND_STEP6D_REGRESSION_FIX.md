# IELTS Backend Step 6D regression correction

## Root cause
The complete_payload() test fixture used floor division to split 40 Reading questions across 3 sections, yielding 13 + 13 + 13 = 39. Production preflight correctly rejected the incomplete fixture.

## Change
Only `bcl/test_step6d_preflight.py` changed. Distribute the remainder to earlier sections: Reading 14/13/13, Listening 10/10/10/10, Writing 1/1. Added a dedicated test checking section and total counts. No changes to production validation, frontend, or database schema.

## Windows 11 verification
Activate the existing venv and ensure the configured test database is isolated. Run:

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test bcl.test_step6d_preflight --verbosity 2
python manage.py test bcl --verbosity 2
```

Expect eight Step 6D tests passing, the full suite passing, and no new migrations. The existing sample `test1.json` is intentionally incomplete and must continue to fail preflight, producing a JSON report and nonzero exit status. Do not import or publish it.

## Release condition
Do not advance to Step 6E until both regression commands pass and the sample preflight still rejects incomplete content.
