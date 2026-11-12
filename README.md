# WordRecall

Save English words with their explanations, then practise typed recall: read an
explanation, type the word, and check your answer. These are the two planned
product features, with accounts and review scheduling handled by the backend.

**Stack:** Expo SDK 58, React Native, TypeScript, and Expo Router for web, iOS,
and Android; FastAPI, PostgreSQL, and Alembic for the backend. Web designs use Figma.

| App identity (D11) | Value |
| --- | --- |
| Display name | WordRecall |
| Expo slug | `wordrecall` |
| iOS bundle ID | `com.jerrynguyen.wordrecall` |
| Android package | `com.jerrynguyen.wordrecall` |

## Local setup

Requires Node.js 24, Python 3.12+ (CI uses 3.13), Docker with Compose, and Expo Go
on your phone. Run commands from the repository root unless stated otherwise.

### 1. Backend and database

```bash
cd backend
cp .env.example .env
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
```

Replace `SECRET_KEY` in `.env` with the generated value, then start the containers:

```bash
docker compose up -d --build
```

This starts PostgreSQL, the API, and the background prompt worker. The API
container applies pending migrations before starting; migration failure stops startup.

The API uses port **8001** by default (`API_PORT` overrides it), with live reload.
PostgreSQL stays on the Pi's loopback interface. Stop containers with
`docker compose down`; data persists. `docker compose down -v` deletes local data.

### 2. Client: web and phone

In another terminal, from the repository root:

```bash
cd client
npm ci
cp .env.example .env.local
REACT_NATIVE_PACKAGER_HOSTNAME=192.168.0.50 npx expo start --go --lan --web
```

Set `EXPO_PUBLIC_API_BASE_URL` in `.env.local` to `http://192.168.0.50:8001`.
Use the Pi's LAN IP, **not localhost**, so your Mac and phone can reach the API.
If the IP changes, update the client URL, the Expo host above, and backend
`CORS_ORIGINS`. Find the Pi's current address with `hostname -I`.

| Service | LAN address |
| --- | --- |
| Web app | <http://192.168.0.50:8081> |
| API docs | <http://192.168.0.50:8001/docs> |
| API health | <http://192.168.0.50:8001/health> |
| Expo Go | `exp://192.168.0.50:8081` |

Connect your phone to the same Wi-Fi and scan the terminal QR code in Expo Go.
Stop Expo with Ctrl+C. `npm run android` and `npm run ios` also support emulators;
the iOS simulator requires macOS and Xcode. Health checks process availability,
not database connectivity.

## Configuration

| Setting | Purpose |
| --- | --- |
| Client `EXPO_PUBLIC_API_BASE_URL` | API endpoint read by `getApiBaseUrl()` in `client/src/constants/api.ts` |
| Client `EXPO_PUBLIC_WEB_API_BASE_URL` | Optional browser API override; defaults to the shared API URL |
| Backend `DATABASE_URL` | Required SQLAlchemy database URL |
| Backend `SECRET_KEY` | Required secret for authentication rate-limit keys |
| Backend `CORS_ORIGINS` | JSON array of exact allowed web origins, such as `["http://192.168.0.50:8081"]`; defaults to none |

The backend reads environment variables before `backend/.env`; Compose overrides
the database URL to use its internal `db` host. For host commands, keep the URL
in `.env` aligned with your PostgreSQL port and credentials.

For preview and production, set the public API URL in the build environment and
supply separate database URLs and secret keys through your hosting provider.
Allow each deployed web origin in CORS. Client variables are embedded at build
time, so rebuild when switching environments. Do not select environments with
`NODE_ENV` or `.env.preview`. Restart the backend after changing its settings.
Authentication and product tables are managed by Alembic.

For browser authentication, the web app and API must use the same site (matching
scheme and hostname; ports may differ). When opening `http://localhost:8081`, set
`EXPO_PUBLIC_WEB_API_BASE_URL=http://localhost:8001` in `client/.env.local` and
restart Expo. Native devices keep using the LAN URL in `EXPO_PUBLIC_API_BASE_URL`.
When opening the web app using the LAN IP, remove the web override or set it to
the same LAN hostname. CORS must allow the web app's exact origin.

After pulling backend changes, rebuild and restart both application processes
from the repository root:

```bash
./devops/deploy_backend.sh start
./devops/deploy_backend.sh status
```

Start/update builds the current source, starts the database, stops the old worker,
and recreates the API. Its startup entrypoint applies all pending forward-only
migrations, including `0014` (saved answer response dates) and `0015` (prompt job
failure tracking). After the new API responds to its internal health check, the
helper recreates the worker. If API startup fails, the worker remains stopped;
inspect `./devops/deploy_backend.sh logs`, fix the cause, and run `start` again.
`/health` on an already-running instance alone does not confirm schema currency.

**Never commit secrets, real `.env` files, keystores, or Apple/Google credentials.**
Use sanitized [client](client/.env.example) and [backend](backend/.env.example)
env examples instead. Never put secrets in `EXPO_PUBLIC_*` variables.

## Development commands

For deployment on `jjnano@192.168.0.108` behind the existing
`vocab.jerryitdev.com` domain, build and deploy directly on the Jetson:

```bash
ssh jjnano@192.168.0.108
cd ~/english-vocab-app
export COMPOSE_PROJECT_NAME=wordrecall
bash devops/deploy-jetson.sh
```

Use the location of the existing checkout if it differs from `~/english-vocab-app`.
The `wordrecall` project selects the existing API and database. Keep the existing
database credentials in the Jetson's private `backend/.env`; optionally add
`COMPOSE_PROJECT_NAME=wordrecall` there to retain the project selection.

Omit `--web-build-dir` when building on the board. With Node 24.3+ or 26+ and npm
available, the script installs client dependencies, builds a production SPA for
the public domain, updates the API and prompt-worker images, applies guarded
forward migrations, and publishes the frontend after local health checks.
The existing database volume is checked before updating, and the working Nginx,
Cloudflare tunnel and DNS are preserved by default.

After deployment, open [vocab.jerryitdev.com](https://vocab.jerryitdev.com).
For setup, troubleshooting and the optional prebuilt-SPA workflow, see the
[Jetson production deployment guide](docs/DEPLOY_JETSON.md).
`devops/publish_production_web.sh` publishes only an already-built frontend;
it does not update the backend.

### Android release builds

Build a signed release APK to install directly on a phone, or an AAB for Google
Play, using Expo's cloud build service. Requires Node.js 24+, npm, network access,
and an Expo account; Android Studio and a local Android SDK are not required.

Sign in once:

```bash
cd client
npx eas-cli@latest login
cd ..
```

Then run from the repository root:

```bash
./devops/build_android_release.sh       # Installable release APK
./devops/build_android_release.sh aab   # Google Play release bundle
```

The script installs missing client dependencies, runs typecheck and lint, uploads
the project, waits for the build, and prints the artifact download link. Download
the APK to your phone and allow installation from that source when prompted.
The AAB is uploaded separately through Google Play Console; the script does not
publish to the store.

On the first interactive build, follow Expo's prompts to create/link the project
and generate or select its Android signing keystore. For an existing published
app, use its existing signing credentials. Keep credentials in Expo's credential
store, outside Git. Commit the public project-link configuration if Expo adds it
to the app config. Later CI builds can use `--non-interactive` after linking and
signing are configured, with `EXPO_TOKEN` supplied through the CI secret store.

Both profiles in `client/eas.json` use `https://vocab.jerryitdev.com` as the public
API URL and automatically increment the Android build number remotely. Change
the profile's public URL before building for a different backend. Local client
environment files are ignored by Git and are not the release configuration.
Only public configuration belongs in the profile's `env` or `EXPO_PUBLIC_*`.
See [Expo's build setup guide](https://docs.expo.dev/build/setup/) and
[APK guide](https://docs.expo.dev/build-reference/apk/) for account and signing details.

### Interactive deployment helpers

Run either menu from any directory:

```bash
./devops/deploy_client.sh
./devops/deploy_backend.sh
```

The client menu builds the web output in `client/dist`, rebuilds with fresh
dependencies and a cleared bundler cache, starts Expo Go/web development, cleans
generated output, edits configuration, and runs checks. The current web output
uses server rendering; building does not publish it to a hosting provider or
produce native app binaries. Development port/host options last for the menu
session, or can be supplied as `CLIENT_PORT=8081 CLIENT_HOST=lan`.

The backend menu builds/rebuilds both API and prompt-worker images and manages
the existing local Docker Compose stack, including status, combined API/worker
logs, prompt queue status, and forward migrations. Start/update recreates both
application containers in migration-safe order, including when only mounted
source files changed; startup retains the guarded migration entrypoint.
This uses the existing development Compose file with live reload,
not a production hosting configuration. Clean asks for confirmation and retains
database volumes and backups; client clean retains configuration and dependencies.

Configure uses `$VISUAL`, `$EDITOR`, or `vi`. Missing environment files are created
from the sanitized examples without overwriting existing files; a new backend
environment receives a generated application secret. Configure the API URLs,
CORS origins and database settings before starting. These private files remain
ignored by Git. Rebuild the client or start/update the backend after edits.

Both scripts also accept a single operation, such as
`./devops/deploy_client.sh build` or `./devops/deploy_backend.sh status`.
Use `--help` for all supported operations. They require Bash; client commands use
Node/npm, backend commands use Docker Compose v2 with `--wait` support, and initial
backend configuration uses Python 3. These helpers never downgrade or stamp the
database.

Useful backend commands from the repository root:

```bash
./devops/deploy_backend.sh start         # Build and run the latest API and worker
./devops/deploy_backend.sh logs          # Follow both application logs
./devops/deploy_backend.sh queue-status  # Counts and failed prompt-job identifiers
```

Configure `OPENROUTER_API_KEY`, `OPENROUTER_URL`, and `OPENROUTER_MODEL` for
text generation. Embeddings continue to use `OLLAMA_URL` and `EMBEDDING_MODEL`.
`PROMPT_JOB_MAX_ATTEMPTS` defaults to 5, including for existing environment files
without this setting. The API and worker share the same database and application
code; the worker handles slow generation independently of HTTP requests. The
`app.prompt_jobs` command is an on-demand administration tool, not another
long-running process.

### Manual database management

Run `./devops/manage_database.sh` to list databases, inspect their details and
tables, create databases, rename them, change their owner, or clear table data. It
connects to the existing backend Compose `db` service, which must already be
running. Direct actions such as `./devops/manage_database.sh list` are also
supported; use `--help` for options.

Rename, owner changes and clearing data require typed confirmation. Clear asks for
the database, schema and table, shows the current row count, then empties that
table while retaining its structure and identity sequences. It never drops a
database or table, and does not cascade to related tables. Foreign-key restrictions
and append-only history protections can reject the operation; they are not bypassed.
System databases/schemas and Alembic migration metadata are protected. Take a
backup before clearing data. `./devops/manage_database.sh clear` opens this operation.
Renaming requires updating dependent connection settings. New databases start
without application tables. Manage application schema changes through new
versioned migrations; this menu does not bypass the migration runner.

### Client checks

From `client/`:

```bash
npm run lint          # ESLint; lint:fix applies fixes
npm run typecheck     # Strict TypeScript
npm test              # API configuration, auth validation, and token-storage tests
npm run check         # Lint, type-check, and formatting check
npm run format        # Apply Prettier formatting
npx expo install <package>
npx expo install --check
```

Screens live in `client/src/app/` with file-based routing. Use Expo's installer
for compatible dependencies (`--dev` for development tools).

For backend checks or running the API outside Docker, from `backend/`:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m nltk.downloader wordnet
python -m ruff check .
python -m mypy
python -m pytest
```

The default tests use temporary SQLite databases and ignore local `.env` settings.
To repeat the API tests against PostgreSQL, set `TEST_POSTGRES_URL` to a local
test database URL and run `python -m pytest tests/api`. Each test creates
and removes its own randomly named schema; existing application tables are untouched.
The database role needs permission to create schemas. CI runs both database paths.

To run the API in this environment, start the database with `docker compose up -d db`,
apply migrations with `python -m app.migrate`, then run
`uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload`.
Stop the Docker API first if it is already using port 8001.

### Database backups

The host runs daily PostgreSQL backups with 30-day retention. See
[backup operations and the completed restore drill](docs/database-backups.md)
for storage, scheduling, monitoring, and recovery instructions.

### Database migrations

Import new models in `backend/app/models/__init__.py`. From `backend/` with the
virtual environment active and database running:

```bash
alembic revision --autogenerate -m "describe schema change"
# Review the generated migration before applying it.
alembic upgrade head
python -m app.migrate  # Same forward-only runner used on deploy
```

The initial migration is an empty baseline. Container startup runs the forward-only
migration runner before starting Uvicorn, including Compose development startup.
For non-container deployments, run `python -m app.migrate` as the release step
before starting API processes. PostgreSQL advisory locking serializes concurrent
runners; migration failure prevents that container from serving traffic.

Never edit, delete, rename, downgrade or stamp a migration that has shipped.
Add a new revision for fixes. CI rejects changes to migration files already in
the PR base or previous push, checks upgrades and schema drift, and runs upgrades
again to verify a no-op. Existing downgrade functions remain historical code;
they are not used by deployment. Keep schema changes compatible with the previous
app version during rolling deployments; use additive changes and defer removal
until all old processes have stopped. Set `APP_ENVIRONMENT=preview` or
`APP_ENVIRONMENT=production` to require a verified persistent backup before every
migration run; backup failure blocks deployment. See the [backup setup](docs/database-backups.md)
for required storage configuration. Recover mistakes with a new forward migration.

## CI

On every push and pull request, GitHub Actions runs client lint, type-checking,
and tests, plus backend Ruff, mypy, pytest, and PostgreSQL migration checks.
CI generates its own temporary secret key.

## Project layout

- `client/` — Cross-platform app and tests.
- `backend/` — API, migrations, and tests.
- `docs/` — [Requirements](docs/requirement.txt), [decisions](docs/decisions.md),
  [planned structure](docs/file_skeleton.md), and design assets.
- `.github/workflows/` — Client and backend CI.

See the [detailed backend architecture diagrams](docs/backend-architecture.md)
for process boundaries, request flows, authentication, review scheduling,
database relationships, background-job recovery, and deployment ordering.

## Authentication

Apply migrations through `0009` before using auth. JSON `POST /api/v1/auth/register` and
`/api/v1/auth/sign-in` accept `email` and `password` (12–128 characters).
Registration also accepts `name`, trimmed to 1–100 characters. The client requires
it at sign-up; it remains optional in the API for older clients. Existing users
retain a null name. The `/me` profile includes `name`.
`POST /api/v1/auth/refresh` and `/api/v1/auth/logout` accept `{}` on web or
`{"refresh_token":"..."}` on native. `GET /api/v1/auth/me` requires
`Authorization: Bearer <access_token>`. Email identities are lowercased.
Passwords use Argon2id with 19 MiB memory, two iterations, one lane, random salts
and rehash on sign-in.

Access tokens expire after 15 minutes. Refresh sessions have a fixed 30-day
lifetime. Each refresh atomically replaces both tokens; only SHA-256 token
digests are stored. Logout immediately revokes the session. Disabled/deleted
users cannot sign in, refresh or access protected routes. Use the
`get_current_user` dependency for future protected routes.

`client/src/services/auth.ts` provides register, signIn, refreshSession (call on
startup), signOut, and authenticatedFetch (one refresh/retry). The Sign up and
Sign in screens follow `docs/Wordwell_Unified_Figma_Import.svg`, with validation,
password visibility controls, accessible labels, and loading/error states. Native refresh tokens use Expo SecureStore;
requests use `X-Auth-Platform: native`. Browser refresh tokens use an HttpOnly,
SameSite=Strict cookie scoped to `/api/v1/auth`. Access tokens stay in memory on both
platforms. Credentials never use localStorage or AsyncStorage.

Startup restores the saved refresh session before exposing authenticated screens.
Temporary network failures keep credentials and the intended route and offer Retry.
Returning from the background rechecks the session. Protected requests refresh
and retry once after an expired access token; rejected refresh credentials notify
the UI to request sign-in. Concurrent requests share refresh work, and late 401
responses reuse a token already rotated by another request.

Expired sessions show Sign in over the current screen, preserving its route,
query parameters, and mounted form state. Signing back into the same account
resumes that screen. A different account or explicit sign-out resets mounted
screens. This preserves active drafts during reauthentication; it does not persist
unsaved form data through process termination. Deep links retain their destination
through startup restoration or reauthentication. Passwords are never persisted.

On web, auth screens use named HTML forms and inputs with username,
current-password/new-password, and name autofill hints. Enter submits from any
input; native keyboards keep Next between fields and Go for password submission.
Tab order follows the visible fields, password visibility control, submit button,
and auth link. Visible focus rings, linked field errors, and focus on failed
validation/server errors support keyboard and screen-reader use. Web submission
reads current form values so password-manager autofill is retained. Validation
starts on submit and updates while editing, avoiding layout shifts during clicks.
The delete confirmation is named and described, initially focuses Cancel, traps
focus, closes on Cancel/Escape when idle, and returns focus to Delete account.


Account displays the profile returned by `/auth/me`. Sign out revokes the current
session. Delete account requires an explicit confirmation before sending an
authenticated `DELETE /api/v1/account`; failed requests keep the account session
available for retry. On success, the client clears its in-memory token/profile,
native SecureStore refresh credential, and mounted account state. Browser deletion
accepts the backend's expired HttpOnly cookie. No password or token is stored in
browser storage, and unrelated browser data is left intact.



Deploy web and API on the same site over HTTPS, such as app.example.com and
api.example.com, and configure the exact web origin in `CORS_ORIGINS`. Cookie
auth POSTs require an allowed Origin. Browsers cannot select native token
responses. `AUTH_COOKIE_SECURE` defaults to true; set false only for local HTTP
development in your untracked backend environment. Unrelated web/API domains
are not supported by this Strict-cookie setup. SecureStore is configured through
the Expo plugin with Android backup exclusions and device-only, unlocked iOS
keychain access. See the [client storage inventory](docs/decisions.md#client-storage--r0--p3)
for permitted persistence and reinstall behavior.

Auth POSTs share a database-backed fixed-window rate limit of 20 requests per
peer IP per minute, including failures, across all workers. Only trust known
reverse proxies in Uvicorn's proxy-header configuration to prevent IP spoofing.
Expired rate buckets are cleaned during auth requests; periodically delete
expired `auth_sessions` rows in deployment. Lifetimes and limits are configurable
in the backend environment example. Do not log auth bodies, tokens, cookies or
Authorization headers.

## Versioned API

Product routes use `/api/v1`; unversioned product routes are not exposed.
`/health`, `/docs`, and `/openapi.json` remain operational/documentation routes.
Client `authenticatedFetch` accepts v1-relative paths, such as `/words`.

| Method | Path | Contract |
| --- | --- | --- |
| POST | `/api/v1/words` | `word`, `english_explanation` → created word (201) |
| GET | `/api/v1/reviews/next?limit=1` | Due items; limit 1–50; empty array when none |
| POST | `/api/v1/reviews/{word_id}/answer` | `typed_answer`, `time_taken_ms` → grading result |
| PATCH | `/api/v1/account` | Validated IANA `timezone` → updated profile (200) |
| DELETE | `/api/v1/account` | Erase account and owned data (204) |

Registration accepts an optional IANA `timezone` (defaults to `UTC`). Existing users
can update it with `PATCH /api/v1/account`; local-day selection changes immediately
without moving existing review due times.

All routes above require a bearer access token. Auth registration, sign-in,
refresh, logout and me routes also use the `/api/v1/auth` prefix.
Creating a word also creates its immediately due review state atomically.
Normalized duplicates within an account return 409. Review items contain only
`word_id` and `english_explanation`, never the word, normalized answer or example.
Explanations are user-supplied text and are returned as entered.

Answer checking uses Unicode NFKC, case folding and collapsed whitespace;
accents and punctuation remain significant. Responses contain `attempt_id`,
`result` (`correct` or `incorrect`), `correct_word`, and `next_due_at`.
Correct answers use SM-2 intervals of 1 day, 6 days, then the prior interval
multiplied by the prior ease factor and rounded up; incorrect answers
reset the level and retry in 10 minutes. Each accepted answer records an immutable
attempt and updates scheduling in one transaction. New attempts retain the resulting
due date so retries return the original response even after later reviews. Attempts
from before migration 0014 have no historical due-date snapshot and retain the
legacy behavior of returning the current due date. Items not yet due return 409
without another attempt. Missing items and another account's items both return
404. Invalid input returns 422. Protected responses disable caching.

Account deletion permanently removes the user, all sessions, words, review states
and attempts in one transaction. Migration `0008` permits history erasure only
when its owner is marked for deletion; ordinary history updates and deletes remain
blocked. Other accounts are untouched. Infrastructure logs/backups follow the
deployment's retention policy. Web sessions from the earlier unversioned API must
sign in again after this version change.

### Data portability (admin)

Operators can produce a private JSON export of a verified user's retained data
with `python -m app.export_user --user-id UUID --output PATH` from `backend/`.
See the [admin procedure](docs/data-portability.md) for scope, delivery and cleanup.
R0 has no in-app export; add one only if an applicable store/privacy requirement
requires it, and update the recorded decision.

### Add-word dictionary search

The Add screen searches the backend’s local Princeton WordNet dictionary through
`GET /api/v1/words/search?q=create&include_family=true&parts=verb&forms=V1`.
Repeat `parts` (noun, verb, adjective, adverb, other) and `forms` (V1, V2, V3)
parameters to select multiple filters. Searches require authentication. Results
can be saved with the existing `POST /api/v1/words` endpoint; duplicate spellings
remain one word-bank entry.

WordNet supplies definitions, examples and lexical derivation relationships;
LemmInflect supplies base, past and past-participle spellings, including irregular
verbs. Family expansion follows up to two lexical relationships, and results
show one definition per spelling and part of speech, capped at 60 entries.
Coverage is dictionary-dependent: WordNet covers nouns, verbs, adjectives and
adverbs, so the Other filter currently returns no entries. This is not a complete
list of every possible derivative or meaning.

Docker builds and CI install the WordNet corpus. For a local backend, run the
download command above once (or set `NLTK_DATA` to an existing corpus directory).
There are no runtime dictionary network calls or API keys. A missing corpus
returns a retryable 503 response. Rebuild the backend image after this change.
WordNet data retains its bundled Princeton license in the installed corpus; see
[WordNet’s license](https://wordnet.princeton.edu/license-and-commercial-use).


### Background review prompt generation

Saving a word returns 201 after storing the word and its generation job in one
transaction. The client does not wait for OpenRouter. A masked example or definition
keeps the word reviewable until the generated prompt is ready. Failures retry
automatically up to `PROMPT_JOB_MAX_ATTEMPTS` (default 5); users do not need to
save the word again. Permanently failed jobs retain their fallback prompts.

Docker Compose includes a separate `prompt-worker` service. Use
`./devops/deploy_backend.sh start` from the repository root to rebuild and start
the latest API and worker in order. The API applies forward-only migrations
through its normal startup procedure; the helper starts the new worker after
the new API is ready. When starting Compose directly, the worker retries database
access while migration is in progress.

For a local installation, run the normal migration command `python -m app.migrate`
from `backend/`, then run `python -m app.prompt_worker` alongside the API using the
same environment. The worker uses the existing `DATABASE_URL`, `OPENROUTER_URL`,
`OPENROUTER_MODEL`, `OPENROUTER_API_KEY`, and `OPENROUTER_TIMEOUT_SECONDS`
settings. No additional broker is required. Keep the worker running to drain the durable queue.
See [review prompt behavior](docs/review-prompt.md) for retries and recovery.

Prompt job logic lives in `backend/app/services/prompt_jobs/`: `worker.py` owns
claiming and generation, and `management.py` owns queue status and retry.
`app.prompt_worker` and `app.prompt_jobs` are thin command entry points.

Operators can inspect queue counts, the oldest pending time, and up to 20 failed
job identifiers without exposing vocabulary or provider messages:

```bash
python -m app.prompt_jobs status
python -m app.prompt_jobs retry --word-id WORD_UUID
```

For the running Compose stack, use `./devops/deploy_backend.sh queue-status`
from the repository root. To reset a failed job, run the following from `backend/`:

```bash
docker compose exec -T api python -m app.prompt_jobs retry --word-id WORD_UUID
```

Run these commands from `backend/` using the deployment environment. Retry accepts
only failed jobs and resets their attempt budget after the cause is fixed. A crash
on the last attempt marks the job failed once its lease expires. Queue categories
distinguish provider HTTP/connection errors, invalid responses, and exhausted
attempts. Multiple-choice preparation analyzes at most 200 saved candidate words
plus the session's 50 targets (201 profiles for a single choice request).
