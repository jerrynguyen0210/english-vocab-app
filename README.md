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
