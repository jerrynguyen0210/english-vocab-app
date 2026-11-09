# English Vocabulary App

A personal app for saving new English words and remembering them through typed recall. The initial focus is personal use, with possible use by friends later.

App identity: **WordRecall**, Expo slug `wordrecall`, iOS bundle identifier and
Android package name `com.jerrynguyen.wordrecall`. See [D11](docs/decisions.md#d11--app-identity).

## Product scope

The app has exactly two product features:

1. **Add a word:** Save an English word with its English explanation.
2. **Typed-recall review:** Read the saved English explanation, type the learned word, and have the app check the answer. No other review modes are planned.

Users have registered accounts. The backend stores words, selects review items, checks answers, and schedules reviews.

## Technology and design

- **Client:** React Native, targeting web, iOS, and Android.
- **Backend:** FastAPI, responsible for the learning logic.
- **Design:** The web UI is designed in Figma.

The project owner writes all implementation code; planning documents contain no source code.

## Project structure

- `client/` — Cross-platform app.
- `backend/` — API and learning logic.
- `docs/` — Requirements, project structure, and design assets.
- `.github/workflows/` — CI workflows.

See [requirements](docs/requirement.txt) for the product requirements and [file skeleton](docs/file_skeleton.md) for the planned directory layout.

## Client development

The client was generated with `npx create-expo-app@latest client --template default --yes` using the SDK 58 default template (TypeScript and Expo Router). TypeScript strict mode is enabled in `client/tsconfig.json`.

```bash
cd client
npm ci
npm start
```

Use `npm run web`, `npm run android`, or `npm run ios` to open a specific platform. The iOS simulator requires macOS and Xcode.

```bash
npm run typecheck    # Check TypeScript
npm run lint         # ESLint using the Expo configuration
npm run lint:fix     # Apply automatic lint fixes
npm run format       # Format with Prettier
npm run format:check # Check formatting without changing files
npm run check        # Run all three checks
```

Install libraries from `client/` with `npx expo install <package>` (or add `--dev` for development tools) so Expo selects SDK-compatible versions where available. Run `npx expo install --check` to verify compatibility.

## Backend development

Requires Python 3.12+ and Docker with Docker Compose. Run these commands from `backend/`:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
cp .env.example .env

docker compose up -d db
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --reload
```

From another device on the same LAN, use the Raspberry Pi's LAN IP:

- API: <http://192.168.0.50:8000>
- Interactive API docs: <http://192.168.0.50:8000/docs>
- Process health: <http://192.168.0.50:8000/health>

`localhost` refers to the device running the browser, so on your Mac it points to
your Mac. Both the Uvicorn command above and the Docker Compose API port bind to
`0.0.0.0` to accept LAN connections. If the Pi's address changes, find its current
LAN IP with `hostname -I` on the Pi and replace `192.168.0.50` in these URLs.
Health does not query the database.
`DATABASE_URL` can be set in `backend/.env` or the shell; shell values take priority.
The example credentials are for local development. If you change the database port
or credentials, update `DATABASE_URL` for host commands as well. URL-encode special
characters in credentials used in a connection URL.

To run both the API (with live reload) and PostgreSQL in containers:

```bash
docker compose up -d --build
docker compose exec api alembic upgrade head
```

Run tests in the virtual environment; the initial API test needs no database:

```bash
python -m pytest
```

Database schema changes use Alembic. Import new SQLAlchemy models in
`app/models/__init__.py` so autogeneration discovers them, then generate and review
an explicit migration before applying it:

```bash
alembic revision --autogenerate -m "describe schema change"
alembic upgrade head
alembic downgrade -1
```

The initial migration is an empty baseline; product tables are not defined yet.
Migrations run explicitly, rather than on API startup. Stop containers with
`docker compose down`; database data stays in the named volume. To intentionally
remove all local database data, use `docker compose down -v`.

## Repository rules

Never commit secrets, real `.env` files, keystores, or Apple/Google credentials
(including signing keys, provisioning profiles, and service-account keys).
Provide a sanitized `.env.example` with placeholder or local-development values
instead. See [backend/.env.example](backend/.env.example) for the backend template.

## Environment configuration

Client API calls should use `getApiBaseUrl()` from `client/src/constants/api.ts`.
For local development, copy `client/.env.example` to `client/.env.local` and set
`EXPO_PUBLIC_API_BASE_URL` to the API address reachable from the device (currently
`http://192.168.0.50:8001` for the Pi). Start the API with `--port 8001` if 8000 is
occupied. For Compose, change the published API port to `0.0.0.0:8001:8000`.

For preview and production builds, set `EXPO_PUBLIC_API_BASE_URL` in the build
provider's environment to the corresponding HTTPS API URL. It is embedded at
bundle time: rebuild/export when changing environments. For a manual build,
set it in the shell before `npx expo export`. Do not use `NODE_ENV` or a
`.env.preview` file to select the API. Only the URL is public; never place backend
secrets in `EXPO_PUBLIC_*` variables.

The backend reads `DATABASE_URL`, `SECRET_KEY`, and `CORS_ORIGINS` from environment
variables, with `backend/.env` as a local fallback. Database URL and secret key are
required. After copying `backend/.env.example` to `backend/.env`, replace the
secret placeholder with a unique value generated by:

```bash
python -c 'import secrets; print(secrets.token_urlsafe(48))'
```

For each deployed environment, supply a separate database URL and secret key via
the hosting provider's secret configuration. Set `CORS_ORIGINS` to a JSON array of
exact web origins, for example `["https://preview.example.com"]` for preview or
`["https://wordrecall.example.com"]` for production. Use the actual client domains;
these are placeholders. The default allows no cross-origin browser access.
Restart the backend after changing settings. Compose loads backend variables from
`.env` and overrides the database host to its internal `db` service. The secret
key is configuration for future authentication; authentication is not implemented yet.
