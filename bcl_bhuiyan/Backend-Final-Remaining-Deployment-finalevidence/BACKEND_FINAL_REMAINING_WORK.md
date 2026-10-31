# IELTS Backend — consolidated final work and release gates

## Fixed in this release

`bcl/test_step6m_exam_assets.py` previously mocked `exists` on `type(section.audio_file.storage)`, which is Django's `DefaultStorage` lazy proxy class. `exists` is delegated to the configured storage instance and is not defined on that proxy class. Both mocks now patch `section.audio_file.storage.exists` on the instance, with an additional regression test for storage failures. The production asset-audit command is unchanged.

## Implementation versus deployment

The core backend contains Django candidate sessions, answer saving, scoring, test-bank import/preflight, PostgreSQL staging audits, media integrity checks, and automated regression coverage. Passing unit tests does **not** prove production acceptance. Do not publish empty test slots or represent this release as production-ready until the following evidence is complete:

1. **Authorized complete exam content**: each publishable test has Reading (3 sections, 40 questions), Listening (4 sections, 40 questions, uploaded audio), Writing (2 tasks), verified answer keys and documented rights. Previously initialized empty slots are not release-ready.
2. **Listening media**: verify protected media access, playback, seeking, expiry and unauthorized access from a real browser, not merely file existence.
3. **Candidate E2E**: browser-driven registration/login, exam start, save/resume, timer expiration, submission, objective scoring, Writing review, results, and candidate isolation on isolated staging.
4. **PostgreSQL**: validate restored staging database identity, counts and representative record checks, backup encryption/retention, restore evidence, and real concurrency tests on disposable PostgreSQL test DB.
5. **Security and operations**: MFA recovery, private-media reverse proxy, production environment and secrets, independent security review, rollback rehearsal, monitoring, and release sign-offs.

## One-run Windows test command

From the extracted `bcl_bhuiyan` project directory with the virtual environment activated and a disposable Django TEST database configured:

```powershell
powershell -ExecutionPolicy Bypass -File .\\RUN_STEP6N_ALL_TESTS.ps1
```

Then point configuration explicitly at **isolated** `ielts_restore_empty` staging and run:

```powershell
powershell -ExecutionPolicy Bypass -File .\\RUN_STEP6N_STAGING_AUDITS.ps1
```

Do not point the test suite at your source database or run destructive commands on staging. The audits are read-only. The audit JSON reports may show unresolved readiness issues; generating a report is not the same as clearing its findings.

## Scope and verification limitations

No backend feature is claimed complete beyond what the repository and tests demonstrate. No production endpoint, migration, scoring logic, or frontend source was modified in this fix. Syntax compilation and archive integrity can be checked here; the Django test suite and PostgreSQL/browser acceptance must be executed in the user's configured environment.
