# Backend Step 6B — Safe initialized-slot content import

## Changes
- `bcl/testbank.py`: allow JSON import into an existing **empty, unpublished** numbered slot, preserving its primary key. Reject published or populated slots and invalid module entries. Existing atomic rollback and separate admin-managed audio uploads remain intact.
- `bcl/test_testbank.py`: six new regression tests for initialized slots, overwrite rejection, published-slot protection, rollback, dry-run, and malformed modules.
- No migrations or frontend changes. Existing data is not included in this source release.

## Windows 11 verification (isolated test environment)
```powershell
cd G:\Shaikat\BCL-Bhuiyan\bcl_bhuiyan
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test bcl.test_testbank --verbosity 2
python manage.py test bcl --verbosity 2
```
Expected: checks without errors, no new migrations, all test-bank tests and full suite pass. The test runner uses a separate test database; verify database settings before invoking it. This ZIP was syntax-checked in the build environment but Django/PostgreSQL integration tests were **not executed** here.

## Staging-only content workflow
1. Confirm DB target is the isolated staging instance, never production.
2. `python manage.py manage_testbank --audit`
3. `python manage.py manage_testbank --import-json test1.json --dry-run`
4. Replace the sample placeholder JSON with fully authorized, complete IELTS content.
5. `python manage.py manage_testbank --import-json completed_test1.json` (only after validation).
6. Upload authorized listening audio through Django Admin, then audit readiness and manually validate candidate workflows before publishing.

**Do not run `--publish` on incomplete sample data.** An imported incomplete slot is intentionally protected against overwriting; use a fresh staging DB to rehearse content import, or develop a separately tested, explicitly authorized content-revision workflow.

## Manual release gates still open
Content licensing, reverse-proxy private-media protection, MFA recovery, full restore/data verification, browser E2E, independent security review, backup encryption and retention. No production go-live claim.

## Interactive verification checklist
- [ ] `python manage.py check` passes
- [ ] No unexpected migrations
- [ ] New regression tests pass
- [ ] Full backend suite passes
- [ ] Empty-slot import dry run rolls back
- [ ] No published/populated test overwritten
- [ ] Authorized content and listening audio staged
- [ ] Manual security and browser gates verified

Next-phase request once all checks pass: `Continue IELTS backend Step 6C: staging content workflow, end-to-end exam verification and production release gate validation using this ZIP as baseline.`
