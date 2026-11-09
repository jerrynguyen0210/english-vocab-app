# English Vocabulary App

A personal app for saving new English words and remembering them through typed recall. The initial focus is personal use, with possible use by friends later.

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
uvicorn app.main:app --reload
```

The API is available at <http://localhost:8000>, interactive API docs at
<http://localhost:8000/docs>, and the process health endpoint at
<http://localhost:8000/health>. Health does not query the database.
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
