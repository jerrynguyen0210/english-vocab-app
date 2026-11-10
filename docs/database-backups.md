# PostgreSQL backups and recovery

PostgreSQL is the source of truth. The host runs `ops/database-backup` daily at
03:15 **host local time** through the `pi5` user's crontab. Cron is an active
system service, so the job does not require an interactive login. The host's
timezone is Australia/Sydney (03:15 is 02:45 Adelaide time). Docker and the
Compose database must be running. Missed jobs while the host is off are not
replayed; run a backup manually after an outage.

## Storage and retention

Archives live in `/home/pi5/.local/state/english-vocab-app/backups`, outside Git.
The directory is mode 0700 and new files are mode 0600. Archives contain private
application data; do not commit or share them. The script uses the database
container's existing credentials without copying secrets into scripts or logs.

Keep each successful backup for **30 elapsed days**. After a new dump succeeds
and its archive index is readable, delete archives older than 30 days and their
SHA-256 sidecars. Failed dumps do not trigger pruning. Partial dumps are removed
on ordinary failure; a hard kill may leave a hidden `.dump.*` file to inspect
and remove manually. The newest successful archive is always preserved.

Each custom-format `pg_dump` is a consistent database snapshot including schema,
data, sequences, and Alembic state. Ownership and grants are deliberately omitted;
cluster roles, credentials, host configuration, and uploaded files are not backed
up by this job. PostgreSQL 17 tools inside the existing container perform both
dump and restore. Use PostgreSQL 17 for the documented drill.

These backups share the host's failure domain. They recover database mistakes,
but do not protect against host/disk loss. An off-host copy is still needed for
that protection. Daily backups give up to approximately 24 hours of data loss
when jobs succeed; this is not point-in-time recovery.

## Install and operate

From the repository root, as the host user with Docker access:

```sh
python3 ops/install-backup-cron
crontab -l
ops/database-backup
```

Re-run the installer if the checkout moves. It preserves unrelated cron jobs.
The scheduled run replaces `latest-backup.log` each day, keeping log storage
bounded. Failure also writes a message with tag `english-vocab-backup` to the
host system log. Check the latest log and archive timestamps daily; there is no
external alert delivery configured. A nonblocking lock prevents overlapping
backup/drill runs. A scheduled run blocked by a drill reports failure.

```sh
cat ~/.local/state/english-vocab-app/backups/latest-backup.log
ls -lt ~/.local/state/english-vocab-app/backups/
journalctl -t english-vocab-backup
```

## Practise recovery

### Required backups before deployment migrations

Set `APP_ENVIRONMENT=preview` or `APP_ENVIRONMENT=production` in each deployment.
Both environments require a new verified custom-format backup before every
`python -m app.migrate` invocation, including no-op runs. The backup runs under
the PostgreSQL migration advisory lock before Alembic changes the schema.
Missing storage, dump errors, archive verification errors, or persistence errors
stop the migration and API startup. Direct online Alembic commands in these
environments are blocked; use the deployment runner. Offline SQL generation
does not back up a database and must not be used to bypass this deployment flow.

Set `MIGRATION_BACKUP_DIR` to an absolute, writable path on persistent storage
for non-Compose deployments, and install PostgreSQL 17 `pg_dump`/`pg_restore`.
The Docker image includes those tools. Compose mounts the host directory
`~/.local/state/english-vocab-app/migration-backups` into the API container;
override `MIGRATION_BACKUP_HOST_DIR` with a separate absolute path for each
preview/production deployment. Rebuild the API image to install the tools.
Do not use ephemeral container storage for backups.

Pre-migration archives and checksum sidecars are retained for **30 days**;
expired archives are pruned only after a successful new backup. This is separate
from the daily backup schedule. Run the restore drill with a pre-migration archive
to verify recovery (the drill accepts either archive naming convention).
Development/test environments retain their existing migration behavior.

Run this monthly and after database/tooling changes, supplying an actual archive:

```sh
ops/database-backup restore-drill /absolute/path/to/vocab-TIMESTAMP.dump
```

The drill verifies the checksum, creates a uniquely named fresh database from
`template0`, and restores in a single transaction with errors fatal. It reads
every public table, reports row counts and the migration revision, and rejects
unvalidated constraints. It removes only the database it created, including on
failure; the source database is never replaced. The current deployment uses the
Compose bootstrap role, which has permission to create and drop drill databases.
This verifies database recovery, not application login or end-to-end behavior.

For a real incident, preserve the damaged database and restore the chosen archive
into a separate database first using `createdb --template=template0` and
`pg_restore --exit-on-error --single-transaction --no-owner --no-acl`. Use the
appropriate database role and verify the restored data before changing the API's
database configuration. Unlike the drill, retain this recovered database. Run
only forward migrations using `python -m app.migrate` when needed; never downgrade
or stamp the deployed database. Coordinate writes and API restart during cutover.

## Completed restore exercise

On 10 November 2026 at 18:02 Adelaide time (07:32 UTC), restored
`vocab-20261110T073215824600878Z.dump` into fresh database
`vocab_restore_20261110_073221_963417` on the host's PostgreSQL 17 instance.
Checksum verification and transactional restore passed. Revision: `0009`.
Restored counts: `alembic_version` 1, `auth_rate_buckets` 1, `auth_sessions` 2,
`review_attempts` 5, `review_states` 3, `users` 1, `words` 3.
All public constraints were validated. The temporary database was removed after
verification, and the source database remained running.
