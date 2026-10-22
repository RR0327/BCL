# IELTS Backend Step 6M — Published content and media audit

## Changes

New read-only command `bcl/management/commands/audit_exam_assets.py` and eight tests in `bcl/test_step6m_exam_assets.py`. No existing production files, frontend files, or migrations changed.

## Windows 11 verification

Activate the existing virtual environment. Use an isolated PostgreSQL test database for tests.

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test bcl.test_step6m_exam_assets --verbosity 2
python manage.py test bcl --verbosity 2
```

Point the configured connection to the **isolated staging** database `ielts_restore_empty` and confirm it before auditing:

```powershell
python manage.py audit_staging --require-postgres --output step6m_staging.json
python manage.py audit_candidate_workflows --require-postgres --output step6m_candidates.json
python manage.py audit_exam_assets --require-postgres --output step6m_assets.json
```

To verify actual media storage references (may access external storage), add `--verify-storage`. To fail when published content has issues, add `--strict`. Both modes remain read-only. The audit intentionally does not expose question text, answers, file paths, or candidate records. Media existence does not establish playback or access-control correctness.

## Acceptance

- System check and no unexpected migrations
- Eight new tests and full suite pass
- Staging audit, candidate audit, and asset audit reports generated
- Existing frontend and backend regression tests pass
- Manual browser playback, content licensing, and release gates still required
