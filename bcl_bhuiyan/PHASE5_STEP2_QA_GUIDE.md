# Phase 5 Step 2 — Quality assurance handoff

## Scope
Adds 12 Django integration/regression tests covering candidate start, autosave, final scoring, attempt ownership, cross-module answer isolation, malformed input, oversized input, violation auto-submission, timeout enforcement, staff/candidate roles, unpublished tests, test-bank atomic rollback, and duplicate protection. Existing test suites remain intact.

## Execute (Windows PowerShell, in bcl_bhuiyan)
```powershell
python -m pip install -r requirements.txt
python manage.py check
python manage.py makemigrations bcl --check --dry-run
python manage.py test bcl.test_phase5_quality --verbosity 2
python manage.py test bcl --verbosity 2
python manage.py manage_testbank --audit
```

## Security and acceptance checks
- Use two different candidate accounts. Neither must access the other's attempts/results.
- Verify an unpublished test cannot be started, even by direct URL.
- Verify a submitted/expired/auto-submitted attempt cannot be edited.
- Verify a second focus-loss report closes an attempt; note that browser focus detection is not secure remote proctoring.
- Verify staff-only writing exports and inspect generated PDF/DOCX.
- Verify no real test content or answer keys are exposed before submission.
- Verify uploaded audio is licensed and content provenance is recorded separately.
- Verify all 30 slots remain unpublished until content passes readiness checks.
- Perform browser tests on Chrome and Edge, including refresh, audio interruption, and slow-network autosave; automated Django tests cannot validate real browser playback.

## Important known limitations
- Phase 5 Step 1 `readiness` checks structural counts and some answer-key rules; it is not a comprehensive editorial/licensing review.
- Existing `manage_testbank --initialize` creates placeholders. Existing `--import-json` refuses to overwrite slots, so plan slot replacement/import workflow before content population.
- Existing local settings use SQLite; proposal calls for PostgreSQL in production. Security audit and production deployment are not complete.
- This update adds tests/documentation, not claims of production security certification.
