# Step 6N — Consolidated Backend Acceptance and Remaining Release Work

## Scope and status
This phase adds a one-pass verification runner and a separate read-only staging audit runner. It does **not** claim that the system is production ready, fabricate test data, or bypass exam content safeguards. The complete Step 6M backend/frontend source is preserved unchanged.

## 1. Run all backend checks once
In PowerShell, activate the venv, navigate to the project root, and run:

```powershell
powershell -ExecutionPolicy Bypass -File .\RUN_STEP6N_ALL_TESTS.ps1
```

The script performs `manage.py check`, `makemigrations --check --dry-run`, and `manage.py test bcl --verbosity 2 --noinput`. Logs and `results.json` are generated in a timestamped folder. A failed check stops the script and must be investigated. Do not assume passing until your Windows output confirms it.

## 2. Audit isolated PostgreSQL staging
**First configure Django to connect to `ielts_restore_empty`, not `ielts_db`, and independently verify your actual DATABASES settings.** The confirmation prompt does not inspect the connection name. Then run:

```powershell
powershell -ExecutionPolicy Bypass -File .\RUN_STEP6N_STAGING_AUDITS.ps1
```

The commands are read-only, but may fail if referenced media is missing. Inspect all JSON reports. `release_acceptance` intentionally produces a report even if automated release gates fail, unless strict mode is enabled.

## 3. Remaining completion requirements
- Import **licensed, complete** examination content for each intended test. Reading: 3 sections/40 questions. Listening: 4 sections/40 questions with valid audio. Writing: 2 tasks. Do not publish incomplete content.
- Validate audio playback through the real media-serving configuration and test Writing evaluation/rubrics with reviewers.
- Run real browser end-to-end journeys: registration/login/MFA, examination start, autosave, timer expiry, submit, scoring/results, Writing review, staff administration, ownership and access controls, session concurrency.
- Reconcile PostgreSQL restore and data counts with backup timestamps, perform restore rehearsal and test encryption/retention.
- Complete the release acceptance manual gates: content licensing, private media reverse proxy, MFA recovery, restore validation, browser E2E, independent security review, backup encryption/retention.
- Re-run strict acceptance only after all test bank content and security requirements are satisfied: `python manage.py release_acceptance --strict --output final_release.json`.

## Release decision
Until the automated acceptance report passes **and** all manual gates have recorded evidence and signoff, the deployment status is **NOT PRODUCTION READY**. This phase consolidates verification; it cannot create licensed exam content or perform real-browser/security acceptance without access to those environments and approvals.
