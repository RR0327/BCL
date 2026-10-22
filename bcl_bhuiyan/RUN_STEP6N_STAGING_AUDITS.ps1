# STEP 6N - READ ONLY STAGING REPORTS. Review DB configuration before running.
# This script deliberately never creates candidate attempts or imports exam content.
$ErrorActionPreference = 'Stop'
Write-Host 'This runs read-only commands against your configured database.'
$confirmation = Read-Host 'Type the EXACT database name ielts_restore_empty to confirm staging'
if ($confirmation -cne 'ielts_restore_empty') { throw 'Cancelled: staging database not confirmed.' }
$reports = Join-Path (Get-Location) 'step6n_staging_reports'
New-Item -ItemType Directory -Path $reports -Force | Out-Null
$commands = @(
    @{Name='staging'; Args=@('audit_staging','--require-postgres','--output',(Join-Path $reports 'staging.json'))},
    @{Name='candidate'; Args=@('audit_candidate_workflows','--require-postgres','--output',(Join-Path $reports 'candidate.json'))},
    @{Name='assets'; Args=@('audit_exam_assets','--require-postgres','--verify-storage','--output',(Join-Path $reports 'assets.json'))},
    @{Name='release'; Args=@('release_acceptance','--output',(Join-Path $reports 'release.json'))}
)
foreach ($cmd in $commands) {
    & python manage.py @($cmd.Args)
    if ($LASTEXITCODE -ne 0) { throw "Staging report failed: $($cmd.Name)" }
}
Write-Host "Reports generated at $reports. Review every issue and manual gate."
