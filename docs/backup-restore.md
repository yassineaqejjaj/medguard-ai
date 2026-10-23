# Backup and restore

What holds state: PostgreSQL (all records and the audit hash chain), SeaweedFS (evidence objects and reports), Valkey (transient
queue only, not backed up) and `.env` (secrets). **Losing `MEDGUARD_SECRET_KEY_B64` makes stored endpoint credentials unreadable.**

## Backup

```bash
scripts/backup.sh          # writes backups/<UTC timestamp>/{medguard.pgdump, evidence.tar, SHA256SUMS}
```

- The PostgreSQL dump is a consistent `pg_dump -Fc` snapshot.
- The evidence archive copies SeaweedFS's data directory while it runs. For a crash-consistent copy, stop SeaweedFS first
  (`docker compose stop seaweedfs`), run the script, then start it again, or snapshot the volume at storage level.
- Copy the folder and a copy of `.env` to storage that is encrypted and separate from the host.

## Restore

```bash
scripts/restore.sh backups/<timestamp> --database restore_test   # rehearsal: restores into a scratch database, touches nothing live
scripts/restore.sh backups/<timestamp>                           # DESTRUCTIVE: replaces the live database and evidence (asks to confirm)
```

The script verifies `SHA256SUMS` before restoring. After a restore, open **Evidence Center, Audit trail**: it must show
"Hash chain verified". Evidence downloads re-check each object against its recorded hash.

Rehearsal recorded during development: a backup of the demo database was restored into a scratch database with identical
row counts (cases, items, audit entries). The restore of the evidence archive into the live stack has not been rehearsed.

## Retention

Settings, Data retention deletes stored responses and reports older than N days. Run metadata, review and release decisions and the
audit trail are kept. Backups are outside this purge: expire them according to your own policy.
