# Step 6B regression-test correction

The previous `test_duplicate_import_rejected` asserted that re-importing an empty unpublished slot must fail. This contradicted the intended Step 6B feature: allowing safe imports into initialized empty slots. The corrected tests allow repeated imports into an empty unpublished slot and still require ValidationError when the slot contains an ExamModule. No production importer changes or migrations are necessary for this particular failure.

Windows PowerShell (inside the project and activated venv):

```powershell
python manage.py check
python manage.py test bcl.test_testbank --verbosity 2
python manage.py test bcl --verbosity 2
python manage.py makemigrations --check --dry-run
```

Run against an isolated Django test database, not your live database.
