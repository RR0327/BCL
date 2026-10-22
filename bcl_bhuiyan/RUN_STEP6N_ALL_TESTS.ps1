# STEP 6N - one-pass automated backend regression verification.
# Run from bcl_bhuiyan with activated venv. Uses Django's disposable TEST database.
# This script does not execute migrations or destructive commands on staging.
$ErrorActionPreference = 'Stop'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$reports = Join-Path (Get-Location) "verification_step6n_$stamp"
New-Item -ItemType Directory -Path $reports -Force | Out-Null
$checks = @(
    @{Name='django_check'; Args=@('manage.py','check')},
    @{Name='migration_drift'; Args=@('manage.py','makemigrations','--check','--dry-run')},
    @{Name='complete_backend_suite'; Args=@('manage.py','test','bcl','--verbosity','2','--noinput')}
)
$results = @()
foreach($check in $checks){
    Write-Host "Running $($check.Name)..."
    $log = Join-Path $reports "$($check.Name).log"
    & python @($check.Args) *>&1 | Out-File -FilePath $log -Encoding utf8
    $code = $LASTEXITCODE
    $results += [pscustomobject]@{name=$check.Name; exit_code=$code; log=$log}
    if($code -ne 0){
        $results | ConvertTo-Json -Depth 3 | Set-Content (Join-Path $reports 'results.json')
        Write-Host "FAILED: $($check.Name). Inspect $log" -ForegroundColor Red
        exit $code
    }
}
$results | ConvertTo-Json -Depth 3 | Set-Content (Join-Path $reports 'results.json')
Write-Host "PASS: All automated Django checks completed. Reports: $reports" -ForegroundColor Green
Write-Host 'NOTE: Production content, browser E2E, and manual security gates are separate.'
