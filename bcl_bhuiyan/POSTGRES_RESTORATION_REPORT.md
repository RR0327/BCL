# PostgreSQL Restoration Report

Date: 2026-10-20
Status: RESTORE COMPLETED; STAGING VALIDATION PASSED

## Databases

- Source: `ielts_db`
- Restore target: `ielts_restore_empty`
- Restore target was confirmed empty with `\\dt` before restoration.
- Both databases use PostgreSQL and all Django migrations are applied.

## Backup and restore

Backup command:

```powershell
python manage.py postgres_rehearsal --destination D:\IELTS_secure_backups
```

Post-migration dump and archive inspection passed with artifact:

```text
D:\IELTS_secure_backups\ielts-postgres-20261019T235610764733Z.dump
```

Restore command:

```powershell
python manage.py postgres_rehearsal `
  --destination D:\IELTS_secure_backups `
  --restore-db ielts_restore_empty `
  --execute-restore `
  --confirm RESTORE-ISOLATED-STAGING
```

Result: `Staging restore command succeeded; verify data and application separately.`

The later attempt to capture a second transcript failed safely because `DB_NAME` was still set to `ielts_restore_empty`; the command rejected using the restore database as its own source:

```text
CommandError: Restoration target must be a different, non-empty staging database name
```

## Reconciliation

The restored database was selected with a process-local `DB_NAME=ielts_restore_empty` value. Django validation returned exit code 0.

| Check | Source `ielts_db` | Restore `ielts_restore_empty` |
|---|---:|---:|
| Users | 0 | 0 |
| Mock tests | 0 | 0 |
| Candidate attempts | 0 | 0 |
| Security audit events | 0 | 0 |
| Django migrations pending | 0 | 0 |

Django `check` passed against the restored database.

## Scope and limitations

The source PostgreSQL database was newly provisioned and contained schema but no migrated SQLite application records. This rehearsal validates PostgreSQL dump creation, archive inspection, isolated restore, migration state, connectivity, and basic application checks. It does not validate migration of the existing SQLite users, test-bank records, attempts, or media.

The dump is not encrypted by `postgres_rehearsal`; it must be encrypted and retained with restricted access before long-term storage.
