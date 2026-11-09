english-vocab-app/
├── README.md
├── .gitignore
├── .github/
│   └── workflows/          # CI: lint and test the app and the API
├── docs/
├── client/                 # React Native + Expo + TypeScript (iOS, Android, web)
└── backend/                # FastAPI + PostgreSQL
    ├── app/
    │   ├── main.py
    │   ├── api/routes/     # auth, words, review
    │   ├── core/           # Settings, security
    │   ├── models/         # Database tables
    │   ├── schemas/        # Request and response shapes
    │   └── services/       # Answer checking, review scheduling
    ├── migrations/         # Database schema changes
    ├── tests/
    ├── Dockerfile
    ├── docker-compose.yml  # Local API + PostgreSQL
    ├── pyproject.toml
    └── .env.example