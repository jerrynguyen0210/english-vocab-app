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
