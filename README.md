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
docker compose exec api alembic upgrade head
```

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
| Backend `DATABASE_URL` | Required SQLAlchemy database URL |
| Backend `SECRET_KEY` | Required secret reserved for future authentication |
| Backend `CORS_ORIGINS` | JSON array of exact allowed web origins, such as `["http://192.168.0.50:8081"]`; defaults to none |

The backend reads environment variables before `backend/.env`; Compose overrides
the database URL to use its internal `db` host. For host commands, keep the URL
in `.env` aligned with your PostgreSQL port and credentials.

For preview and production, set the public API URL in the build environment and
supply separate database URLs and secret keys through your hosting provider.
Allow each deployed web origin in CORS. Client variables are embedded at build
time, so rebuild when switching environments. Do not select environments with
`NODE_ENV` or `.env.preview`. Restart the backend after changing its settings.
Authentication and product database tables are not implemented yet.

**Never commit secrets, real `.env` files, keystores, or Apple/Google credentials.**
Use sanitized [client](client/.env.example) and [backend](backend/.env.example)
env examples instead. Never put secrets in `EXPO_PUBLIC_*` variables.

## Development commands

From `client/`:

```bash
npm run lint          # ESLint; lint:fix applies fixes
npm run typecheck     # Strict TypeScript
npm test              # API configuration tests (Node test runner)
npm run check         # Lint, type-check, and formatting check
npm run format        # Apply Prettier formatting
npx expo install <package>
npx expo install --check
```

Screens live in `client/src/app/` with file-based routing. Use Expo's installer
for compatible dependencies (`--dev` for development tools). The starter reset
utility, `npm run reset-project`, can move or delete starter files; it is optional.

For backend checks or running the API outside Docker, from `backend/`:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m ruff check .
python -m mypy
python -m pytest
```

To run the API in this environment, start the database with `docker compose up -d db`,
apply migrations with `alembic upgrade head`, then run
`uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload`.
Stop the Docker API first if it is already using port 8001.

### Database migrations

Import new models in `backend/app/models/__init__.py`. From `backend/` with the
virtual environment active and database running:

```bash
alembic revision --autogenerate -m "describe schema change"
# Review the generated migration before applying it.
alembic upgrade head
alembic downgrade -1   # Roll back one revision
```

The initial migration is an empty baseline. Migrations run explicitly.

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
