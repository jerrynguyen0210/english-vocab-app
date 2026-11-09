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
