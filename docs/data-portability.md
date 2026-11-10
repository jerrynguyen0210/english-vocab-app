# Admin data portability procedure

R0 provides data portability as a backend operator task, not an in-app feature.
Use `python -m app.export_user` with backend database access. There is no public
export endpoint, download URL, admin role in the app, or schema migration.

## Fulfil a request

1. Verify the requester and their entitlement through the support process.
   Resolve the account's UUID from the verified account record; do not select
   an account based only on an unverified email supplied in a message.
2. Use the intended environment's backend configuration and restricted operator
   access. Prefer a database role with SELECT-only access. The command uses the
   existing `DATABASE_URL`; do not put credentials on the command line.
3. Create a private working directory outside the repository and run from
   `backend/` with its virtual environment active:

   ```sh
   install -d -m 700 "$HOME/.local/state/english-vocab-app/exports"
   python -m app.export_user \
     --user-id VERIFIED-ACCOUNT-UUID \
     --output "$HOME/.local/state/english-vocab-app/exports/user-data-REQUEST-ID.json"
   ```

   Replace both placeholders. The parent directory must exist. Output is UTF-8
   JSON with UTC timestamps, UUIDs and `format_version: 1`. The file is created
   with mode 0600; existing files and symlinks are refused. A missing account
   produces no file. No personal data is printed to stdout. The entire export
   is assembled in memory, suitable for R0 account sizes; evaluate streaming
   before using this for unusually large accounts.
4. Check the account UUID, collection counts and content against the verified
   request in a private environment. Deliver using an authenticated, restricted
   transfer method agreed with the requester. Do not attach exports to public
   issues, commit them, or place them on publicly served storage.
5. Record request ID, verified account UUID, operator, export time, delivery
   outcome and deletion date in the restricted support record, not application
   logs or Git. Delete working/delivery copies after confirmed delivery, and
   within **7 days of generation** at the latest. If another copy is required,
   regenerate it after verification. This cleanup is an operator step, not an
   automated retention job. Database backup retention is separate.

For Compose, execute the module in the running API container with
`docker compose exec -T api python -m app.export_user ...` and an output path in
an operator-provided private mount. Do not use `docker compose run` without
an entrypoint override: the normal image entrypoint runs deployment migrations.
A failed export must be investigated before delivery; never send a partial file.

## Included and excluded data

Included: account identity/name/email/provider identifier/timezone/lifecycle
fields; saved words, explanations and examples; current SM-2 scheduling state and
counts; complete retained review attempt history including typed answers and
elapsed time; session IDs, platform and expiry timestamps.

Excluded: password hashes, access/refresh credentials and their hashes, shared
IP-based rate-limit buckets, operational logs and database backups. Rate-limit
buckets cannot reliably be attributed to one user. This is an application-data
export of currently retained records, not an assertion that every possible
privacy request is satisfied: separately assess any request covering operational
records or other systems. Deleted accounts are not reconstructed from backups
by this command. Credential material is never included.

Every collection is scoped to the selected UUID; scheduling rows are selected
through that user's words. PostgreSQL exports run in a read-only repeatable-read
transaction so simultaneous reviews or account changes cannot mix snapshots.
The export neither alters review history nor migrates the database. When adding
new user-owned tables/fields, update the explicit export list and isolation tests.
