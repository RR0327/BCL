# Listening isolation and Back navigation — development hotfix

## Changes
- `bcl/exam_views.py`: disabled an obsolete client bridge which submitted whenever `checkAnswers` ran. Official submission remains with the active Listening bridge.
- Removed automatic submission of Listening from the Reading GET handler. Reading remains blocked until Listening was actually submitted, expired, or auto-submitted by existing examination integrity policies.
- Added an optional per-attempt ID check to the Listening POST handler. The current Listening frontend sends its attempt ID, while older clients without the field continue to work.
- On browser Back/Forward navigation, the Listening playback position is reset to zero; on BFCache restoration, tracks are paused, rewound, and the instruction screen is shown. Ordinary refresh continues the existing playback policy.
- Added regression tests for independent mock submissions, session mismatch, and Reading sequence guard.

## Mock 8 audio — unresolved external asset dependency
`listening/listening-mock-8.html` uses an Internet Archive URL (an external MP3) in `audioSource`. No official Mock 8 MP3 was included in the uploaded ZIP. The correctness and availability of this file cannot be verified from this offline environment. Do not substitute a different test's MP3: obtain the correct licensed audio, put it at `static/listening_audio/mock_8_full.mp3`, and verify the file plays end-to-end; the injected audio engine automatically prefers the local merged file.

## Windows 11 verification
From the repository root, using an activated project virtual environment:

```powershell
python -m pip install -r requirements.txt
python manage.py check
python manage.py test bcl.test_listening_isolation_regression --verbosity 2
python manage.py test bcl.test_architecture_listening --verbosity 2
python manage.py runserver
```

Expected for the new regression suite: 4 tests discovered and passing; `manage.py check` reports no system-check issues. Existing architecture tests may contain older assumptions and must be reviewed if failures occur. Tests were NOT executed in the artifact-building environment because Django was not installed and package download was unavailable.

## Browser checklist
- [ ] Practice Mock 8 Listening and Mock 9 Listening independently; submit only Mock 8, verify Mock 9 remains in progress.
- [ ] During Full Mock Listening, attempt to open the Reading URL; confirm Listening remains active and no completion banner is shown.
- [ ] Submit Listening explicitly in a Full Mock; verify Reading becomes available.
- [ ] With Listening playing, navigate away and click browser Back; verify 00:00 on return.
- [ ] Refresh the active Listening page; verify behavior remains consistent with the continuous-audio examination policy.
- [ ] Supply and verify the correct official Mock 8 audio; confirm it loads and plays through completion.
- [ ] Run the full backend regression suite on Windows and investigate any failures.

When all are checked, the next suggested command is: `Continue BCL-Bhuiyan Listening regression acceptance, using the latest validated project ZIP and Windows test results; no new development phases unless evidence requires them.`
