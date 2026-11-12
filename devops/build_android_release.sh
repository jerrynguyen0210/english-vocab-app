#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
CLIENT_DIR=$(cd -- "$SCRIPT_DIR/../client" && pwd)

usage() {
    cat <<'EOF'
Usage: ./devops/build_android_release.sh [apk|aab] [--non-interactive]

Build a signed Android release using Expo's cloud build service.
  apk                  Install directly on an Android phone (default).
  aab                  Google Play release bundle.
  --non-interactive    For CI with an already-linked project and signing setup.
  -h, --help           Show this help.

Requires Node.js 24+, npm, network access, and an Expo account.
First sign in from client/: npx eas-cli@latest login
The first interactive build can link the project and configure remote signing.
The production API URL is configured in client/eas.json.
The command waits for the build and prints its download link.
EOF
}

format=apk
format_set=false
build_options=()
for argument in "$@"; do
    case "$argument" in
        apk|aab)
            if [[ "$format_set" == true ]]; then
                printf 'Choose only one output format: apk or aab.\n' >&2
                exit 2
            fi
            format=$argument
            format_set=true
            ;;
        --non-interactive) build_options+=(--non-interactive) ;;
        -h|--help) usage; exit 0 ;;
        *) printf 'Unknown argument: %s\n' "$argument" >&2; usage >&2; exit 2 ;;
    esac
done

for command in node npm npx; do
    command -v "$command" >/dev/null 2>&1 || {
        printf 'Required command not found: %s\n' "$command" >&2
        exit 1
    }
done

cd -- "$CLIENT_DIR"
if [[ ! -f node_modules/expo/bin/cli ]]; then
    npm ci
fi

printf 'Checking the client before building the Android release...\n'
npm run typecheck
npm run lint

profile=release-apk
if [[ "$format" == aab ]]; then
    profile=production
fi

printf 'Building signed Android %s with profile %s.\n' "$format" "$profile"
exec npx --yes eas-cli@latest build --platform android --profile "$profile" --wait "${build_options[@]}"
