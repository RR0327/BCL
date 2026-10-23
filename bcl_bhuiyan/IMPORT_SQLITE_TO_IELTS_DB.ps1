# ==============================================================================
# SCRIPT: IMPORT_SQLITE_TO_IELTS_DB.ps1
# PURPOSE: Clear all tables/data in PostgreSQL 'ielts_db', export data from
#          'db.sqlite3' with UTF-8 encoding, migrate fresh, import data,
#          and reset PostgreSQL ID sequences.
# ==============================================================================

$ErrorActionPreference = 'Stop'

Write-Host "=== IELTS Database Migration: SQLite -> PostgreSQL (ielts_db) ===" -ForegroundColor Cyan

# 1. Verify db.sqlite3 exists
if (-not (Test-Path "db.sqlite3")) {
    Write-Error "db.sqlite3 not found in current directory. Run this script from bcl_bhuiyan."
    exit 1
}

# 2. Export data from SQLite
Write-Host "`n[1/5] Exporting clean data from db.sqlite3 (UTF-8)..." -ForegroundColor Yellow
$dumpFile = "sqlite_data_export.json"
$env:PYTHONUTF8 = "1"
$env:DB_ENGINE = "sqlite3"
$env:DB_NAME = "db.sqlite3"

python manage.py dumpdata `
    --natural-foreign `
    --natural-primary `
    --exclude contenttypes `
    --exclude auth.permission `
    --indent 2 `
    --output $dumpFile

if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to dump data from SQLite."
    exit $LASTEXITCODE
}
Write-Host "Export successful: $dumpFile" -ForegroundColor Green

# 3. Clear ielts_db schema in PostgreSQL
Write-Host "`n[2/5] Resetting 'public' schema in PostgreSQL database 'ielts_db'..." -ForegroundColor Yellow
$env:DB_ENGINE = "postgresql"
$env:DB_NAME = "ielts_db"

python -c "import psycopg; conn = psycopg.connect('dbname=ielts_db user=ielts_app password=Siam@456 host=127.0.0.1 port=5432', autocommit=True); conn.execute('DROP SCHEMA public CASCADE; CREATE SCHEMA public;'); conn.execute('GRANT ALL ON SCHEMA public TO ielts_app;'); print('Schema public reset.')"

if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to reset public schema in ielts_db."
    exit $LASTEXITCODE
}

# 4. Run Django migrations to recreate tables fresh
Write-Host "`n[3/5] Applying Django migrations to ielts_db..." -ForegroundColor Yellow
python manage.py migrate

if ($LASTEXITCODE -ne 0) {
    Write-Error "Migrations failed on ielts_db."
    exit $LASTEXITCODE
}

# 5. Load exported SQLite data into PostgreSQL
Write-Host "`n[4/5] Loading data into ielts_db..." -ForegroundColor Yellow
python manage.py loaddata $dumpFile

if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to load data into ielts_db."
    exit $LASTEXITCODE
}

# 6. Reset PostgreSQL ID sequences to prevent duplicate key errors on future inserts
Write-Host "`n[5/5] Synchronizing PostgreSQL auto-increment sequences..." -ForegroundColor Yellow
python -c "import subprocess, sys, psycopg; r = subprocess.run([sys.executable, 'manage.py', 'sqlsequencereset', 'bcl', 'auth', 'axes', 'otp_totp', 'admin'], capture_output=True, text=True); conn = psycopg.connect('dbname=ielts_db user=ielts_app password=Siam@456 host=127.0.0.1 port=5432', autocommit=True); conn.execute(r.stdout); print('Sequences synchronized successfully.')"

# Update .env to ielts_db if needed
$envContent = Get-Content ".env" -Raw
if ($envContent -match 'DB_NAME=ielts_restore_empty') {
    $envContent = $envContent -replace 'DB_NAME=ielts_restore_empty', 'DB_NAME=ielts_db'
    Set-Content ".env" $envContent -NoNewline
    Write-Host ".env DB_NAME set to ielts_db." -ForegroundColor Cyan
}

Write-Host "`n=== Migration Complete! ===" -ForegroundColor Green
Write-Host "PostgreSQL 'ielts_db' now contains all data from 'db.sqlite3'."
Write-Host "Temporary dump retained at: $dumpFile (you can remove it if desired)."
