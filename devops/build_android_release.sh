#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
CLIENT_DIR=$(cd -- "$SCRIPT_DIR/../client" && pwd)
OUTPUT_DIR="$SCRIPT_DIR/../build/android"

usage() {
    cat <<'EOF'
Usage: ./devops/build_android_release.sh [apk|aab] [--non-interactive]
       ./devops/build_android_release.sh [apk|aab] --download-build BUILD_ID

Build a signed Android release using Expo's cloud build service.
  apk                  Install directly on an Android phone (default).
  aab                  Google Play release bundle.
  --non-interactive    For CI with an already-linked project and signing setup.
  --download-build ID  Download an existing finished build without rebuilding.
  -h, --help           Show this help.

Requires Node.js 24+, npm, curl, unzip, network access, and an Expo account.
First sign in from client/: npx eas-cli@latest login
The first interactive build can link the project and configure remote signing.
The production API URL is configured in client/eas.json.
The command waits for the build, downloads and checks the artifact, and prints
its local path and download link. Files are saved under build/android/.
EOF
}

format=apk
format_set=false
# Bash 3.2 (macOS) treats an empty array as unset under `set -u`.
build_options=(--wait)
build_id=''
while [[ $# -gt 0 ]]; do
    argument=$1
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
        --download-build)
            if [[ $# -lt 2 || -n "$build_id" ]]; then
                printf 'Provide one build ID after --download-build.\n' >&2
                exit 2
            fi
            build_id=$2
            if [[ ! "$build_id" =~ ^[[:xdigit:]]{8}-[[:xdigit:]]{4}-[[:xdigit:]]{4}-[[:xdigit:]]{4}-[[:xdigit:]]{12}$ ]]; then
                printf 'Invalid Expo build ID: %s\n' "$build_id" >&2
                exit 2
            fi
            shift
            ;;
        -h|--help) usage; exit 0 ;;
        *) printf 'Unknown argument: %s\n' "$argument" >&2; usage >&2; exit 2 ;;
    esac
    shift
done

for command in node npm npx curl unzip; do
    command -v "$command" >/dev/null 2>&1 || {
        printf 'Required command not found: %s\n' "$command" >&2
        exit 1
    }
done

node -e 'if (Number(process.versions.node.split(".")[0]) < 24) { console.error("Node.js 24+ is required."); process.exit(1); }'

work_dir=$(mktemp -d)
download_file=''
cleanup() {
    rm -rf -- "$work_dir"
    if [[ -n "$download_file" ]]; then
        rm -f -- "$download_file"
    fi
}
trap cleanup EXIT

cd -- "$CLIENT_DIR"
if [[ -z "$build_id" ]]; then
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
    # Keep interactive project/signing prompts available. JSON mode would force
    # non-interactive mode, so capture this command's exact build URL instead.
    npx --yes eas-cli@latest build --platform android --profile "$profile" "${build_options[@]}" \
        | tee "$work_dir/build.log"
    build_id=$(node - "$work_dir/build.log" <<'JS'
    const fs = require('node:fs');
    const log = fs.readFileSync(process.argv[2], 'utf8');
    const ids = [...log.matchAll(/https:\/\/expo\.dev\/accounts\/[^/\s]+\/projects\/[^/\s]+\/builds\/([a-f0-9-]{36})/gi)]
      .map(match => match[1]);
    const unique = [...new Set(ids)];
    if (unique.length !== 1) {
      console.error('Could not identify the exact build. Download it from the Expo build page.');
      process.exit(1);
    }
    console.log(unique[0]);
JS
    )
fi

printf 'Fetching Android build %s...\n' "$build_id"
npx --yes eas-cli@latest build:view "$build_id" --json > "$work_dir/build.json"
node - "$work_dir/build.json" "$format" "$build_id" > "$work_dir/artifact.txt" <<'JS'
const fs = require('node:fs');
const [file, format, id] = process.argv.slice(2);
const build = JSON.parse(fs.readFileSync(file, 'utf8'));
const artifact = build.artifacts?.applicationArchiveUrl || build.artifacts?.buildUrl;
if (build.id !== id || build.platform !== 'ANDROID' || build.status !== 'FINISHED' || !artifact) {
  console.error('The requested Android build has not finished successfully or has no artifact.');
  process.exit(1);
}
const url = new URL(artifact);
if (url.protocol !== 'https:' || !url.pathname.endsWith(`.${format}`)) {
  console.error(`The build does not have an HTTPS .${format} artifact. Check the requested format.`);
  process.exit(1);
}
const safe = value => String(value ?? 'unknown').replace(/[^a-zA-Z0-9._-]/g, '_');
console.log(artifact);
console.log(`WordRecall-${safe(build.appVersion)}-build${safe(build.appBuildVersion)}-${id}-release.${format}`);
JS
artifact_url=$(sed -n '1p' "$work_dir/artifact.txt")
artifact_name=$(sed -n '2p' "$work_dir/artifact.txt")
mkdir -p -- "$OUTPUT_DIR"
OUTPUT_DIR=$(cd -- "$OUTPUT_DIR" && pwd)
download_file=$(mktemp "$OUTPUT_DIR/.android-release.XXXXXX")
printf 'Downloading %s...\n' "$artifact_name"
curl --fail --location --retry 3 --connect-timeout 30 --max-time 600 \
    --proto '=https' --proto-redir '=https' "$artifact_url" --output "$download_file"
unzip -tqq "$download_file"
manifest=AndroidManifest.xml
if [[ "$format" == aab ]]; then
    manifest=base/manifest/AndroidManifest.xml
fi
unzip -p "$download_file" "$manifest" > /dev/null
mv -f -- "$download_file" "$OUTPUT_DIR/$artifact_name"
download_file=''
printf '\nRelease archive verified.\nSaved: %s/%s\nDownload: %s\n' "$OUTPUT_DIR" "$artifact_name" "$artifact_url"
