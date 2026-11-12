#!/usr/bin/env bash
set -uo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd) || exit 1
BACKEND_DIR=$(cd -- "$SCRIPT_DIR/../backend" && pwd) || exit 1
BACKEND_COMPOSE_FILE=${BACKEND_COMPOSE_FILE:-$BACKEND_DIR/docker-compose.yml}

require_command() {
    command -v "$1" >/dev/null 2>&1 || {
        printf 'Required command not found: %s\n' "$1" >&2
        return 1
    }
}

compose() {
    require_command docker || return
    docker compose version >/dev/null 2>&1 || {
        printf 'Docker Compose v2 is required.\n' >&2
        return 1
    }
    if [[ ! -f "$BACKEND_DIR/.env" ]]; then
        printf 'Backend environment is missing. Select Configure first.\n' >&2
        return 1
    fi
    (
        cd -- "$BACKEND_DIR" || exit 1
        docker compose --project-directory "$BACKEND_DIR" -f "$BACKEND_COMPOSE_FILE" "$@"
    )
}

configure_backend() {
    local -a editor_command
    read -r -a editor_command <<< "${VISUAL:-${EDITOR:-vi}}"
    require_command "${editor_command[0]}" || return
    if [[ ! -e "$BACKEND_DIR/.env" && ! -L "$BACKEND_DIR/.env" ]]; then
        require_command python3 || return
        python3 - "$BACKEND_DIR" <<'PY' || return
import os
import secrets
import sys
from pathlib import Path

directory = Path(sys.argv[1])
template = (directory / ".env.example").read_text()
content = template.replace("replace-with-a-generated-secret", secrets.token_urlsafe(48))
descriptor = os.open(directory / ".env", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(descriptor, "w") as output:
    output.write(content)
PY
        printf 'Created private backend configuration with a generated application secret.\n'
    fi
    printf 'Edit database, CORS, cookie and review options. API_PORT defaults to 8001.\n'
    printf 'Set OLLAMA_URL, OLLAMA_MODEL and PROMPT_JOB_MAX_ATTEMPTS for background prompt generation.\n'
    printf 'This Compose file runs the local development stack. Database credentials must match existing data.\n'
    printf 'Preview/production migration backups require APP_ENVIRONMENT and persistent MIGRATION_BACKUP_HOST_DIR.\n'
    "${editor_command[@]}" "$BACKEND_DIR/.env" || return
    printf 'Use Start / update to apply environment changes. Existing configuration was not replaced.\n'
}

build_backend() {
    compose build api prompt-worker embedding-worker
}

rebuild_backend() {
    compose build --no-cache --pull api prompt-worker embedding-worker
}

wait_for_api() {
    # Probe inside the newly recreated API container, so host port overrides
    # and a previous API instance cannot produce a false readiness result.
    compose exec -T api python - <<'PY'
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

deadline = time.monotonic() + 120
while time.monotonic() < deadline:
    try:
        with urlopen("http://127.0.0.1:8000/health", timeout=2) as response:
            if response.status == 200:
                print("API ready; startup migrations completed.")
                sys.exit(0)
    except (URLError, OSError):
        pass
    time.sleep(1)
sys.exit("API did not become ready. Check API logs for startup or migration failures.")
PY
}

start_backend() {
    if [[ -f "$BACKEND_DIR/.env" ]] &&
        grep -Eq '^[[:space:]]*SECRET_KEY[[:space:]]*=.*replace-with-a-generated-secret' "$BACKEND_DIR/.env"; then
        printf 'Replace the example SECRET_KEY using Configure before starting.\n' >&2
        return 1
    fi
    printf 'Building the API and background workers from the current backend source.\n'
    build_backend || return
    compose up -d --wait --wait-timeout 120 db || return
    # Stop old worker code before applying new schema changes. Always recreate
    # all application containers, including when only bind-mounted code changed.
    compose stop prompt-worker embedding-worker || return
    printf 'Starting the API; its entrypoint applies guarded forward migrations.\n'
    compose up -d --no-deps --force-recreate --wait --wait-timeout 120 api || return
    if ! wait_for_api; then
        printf 'Background workers remain stopped. Fix API startup, then run Start / update again.\n' >&2
        return 1
    fi
    compose up -d --no-deps --force-recreate --wait --wait-timeout 120 prompt-worker embedding-worker || return
    compose ps db api prompt-worker embedding-worker
}

clean_backend() {
    local answer
    printf 'Stop and remove this Compose stack and its local images? Database volumes and backups are kept.\n'
    read -r -p 'Type yes to clean: ' answer || return 1
    [[ "$answer" == yes ]] || { printf 'Clean cancelled.\n'; return 1; }
    compose down --remove-orphans --rmi local
}

usage() {
    printf 'Usage: %s [build|rebuild|start|stop|clean|configure|status|logs|queue-status|migrate|--help]\n' "$0"
    printf 'No argument opens the menu. Uses backend/docker-compose.yml (local development stack).\n'
    printf 'BACKEND_COMPOSE_FILE can select backend/docker-compose.jetson.yml for production.\n'
    printf 'Clean retains database volumes and backups. VISUAL or EDITOR selects the configuration editor.\n'
}

run_action() {
    case "$1" in
        1|build) build_backend ;;
        2|rebuild) rebuild_backend ;;
        3|start) start_backend ;;
        4|stop) compose stop ;;
        5|clean) clean_backend ;;
        6|configure) configure_backend ;;
        7|status) compose ps ;;
        8|logs) compose logs --tail 100 --follow api prompt-worker embedding-worker ;;
        9|migrate) compose exec api python -m app.migrate ;;
        10|queue-status) compose exec -T api python -m app.prompt_jobs status ;;
        -h|--help) usage ;;
        *) printf 'Unknown operation: %s\n' "$1" >&2; usage >&2; return 2 ;;
    esac
}

if (($# > 1)); then
    usage >&2
    exit 2
fi
if (($# == 1)); then
    run_action "$1"
    exit $?
fi

trap 'printf "\nOperation interrupted.\n" >&2' INT
while true; do
    printf '\n=== WordRecall backend (Docker Compose development stack) ===\n'
    printf '1) Build API and worker images\n2) Rebuild API and worker images (no cache, refresh base image)\n3) Start / update stack\n4) Stop stack\n5) Clean containers and local images (keep database)\n6) Configure options\n7) Show status\n8) Follow API and worker logs (Ctrl+C to stop)\n9) Apply forward migrations\n10) Show prompt queue status\n0) Exit\n'
    read -r -p 'Select operation: ' choice || break
    [[ "$choice" == 0 ]] && break
    if run_action "$choice"; then
        printf 'Operation completed.\n'
    else
        printf 'Operation failed or was cancelled; see the message above.\n' >&2
    fi
done
