#!/usr/bin/env bash
set -uo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd) || exit 1
CLIENT_DIR=$(cd -- "$SCRIPT_DIR/../client" && pwd) || exit 1
CLIENT_PORT=${CLIENT_PORT:-8081}
CLIENT_HOST=${CLIENT_HOST:-lan}

require_command() {
    command -v "$1" >/dev/null 2>&1 || {
        printf 'Required command not found: %s\n' "$1" >&2
        return 1
    }
}

install_dependencies() {
    require_command npm || return
    (cd -- "$CLIENT_DIR" && npm ci)
}

ensure_dependencies() {
    require_command node || return
    if [[ ! -f "$CLIENT_DIR/node_modules/expo/bin/cli" ]]; then
        install_dependencies || return
    fi
}

build_client() {
    ensure_dependencies || return
    (
        cd -- "$CLIENT_DIR" || exit 1
        node node_modules/expo/bin/cli export --platform web --output-dir dist "$@"
    ) || return
    printf 'Web build created in %s/dist (server output; hosting is a separate step).\n' "$CLIENT_DIR"
}

rebuild_client() {
    install_dependencies && build_client --clear
}

start_client() {
    if [[ ! "$CLIENT_PORT" =~ ^[0-9]{1,5}$ ]] ||
        ((10#$CLIENT_PORT < 1 || 10#$CLIENT_PORT > 65535)); then
        printf 'CLIENT_PORT must be a number between 1 and 65535.\n' >&2
        return 1
    fi
    case "$CLIENT_HOST" in
        lan|localhost) ;;
        *) printf 'CLIENT_HOST must be lan or localhost.\n' >&2; return 1 ;;
    esac
    ensure_dependencies || return
    printf 'Starting development server. Press Ctrl+C to stop.\n'
    (
        cd -- "$CLIENT_DIR" || exit 1
        node node_modules/expo/bin/cli start --go --web --host "$CLIENT_HOST" --port "$CLIENT_PORT"
    )
}

clean_client() {
    local answer
    printf 'Stop any running client server first. Remove dist and .expo? Configuration and dependencies are kept.\n'
    read -r -p 'Type yes to clean: ' answer || return 1
    [[ "$answer" == yes ]] || { printf 'Clean cancelled.\n'; return 1; }
    rm -rf -- "$CLIENT_DIR/dist" "$CLIENT_DIR/.expo"
}

edit_environment() {
    local -a editor_command
    read -r -a editor_command <<< "${VISUAL:-${EDITOR:-vi}}"
    require_command "${editor_command[0]}" || return
    if [[ ! -e "$CLIENT_DIR/.env.local" && ! -L "$CLIENT_DIR/.env.local" ]]; then
        (umask 077; set -o noclobber; cat -- "$CLIENT_DIR/.env.example" > "$CLIENT_DIR/.env.local") || return
    fi
    printf 'Edit public API URLs only; EXPO_PUBLIC values are embedded in the app. Rebuild after changes.\n'
    "${editor_command[@]}" "$CLIENT_DIR/.env.local"
}

configure_client() {
    local choice port host
    printf '\n1) Edit API environment configuration\n2) Set development server options (this session)\n0) Back\n'
    read -r -p 'Select configuration: ' choice || return 1
    case "$choice" in
        1) edit_environment ;;
        2)
            read -r -p "Port [$CLIENT_PORT]: " port || return 1
            read -r -p "Host: lan or localhost [$CLIENT_HOST]: " host || return 1
            port=${port:-$CLIENT_PORT}
            host=${host:-$CLIENT_HOST}
            if [[ ! "$port" =~ ^[0-9]{1,5}$ ]] || ((10#$port < 1 || 10#$port > 65535)); then
                printf 'Invalid port.\n' >&2
                return 1
            fi
            case "$host" in
                lan|localhost) ;;
                *) printf 'Invalid host.\n' >&2; return 1 ;;
            esac
            CLIENT_PORT=$port
            CLIENT_HOST=$host
            printf 'Development options updated for this script session.\n'
            ;;
        0) return 0 ;;
        *) printf 'Unknown configuration choice.\n' >&2; return 2 ;;
    esac
}

check_client() {
    ensure_dependencies || return
    require_command npm || return
    (cd -- "$CLIENT_DIR" && npm run typecheck && npm run lint && npm test)
}

usage() {
    printf 'Usage: %s [build|rebuild|start|clean|configure|install|check|--help]\n' "$0"
    printf 'No argument opens the menu. Build exports web server output; it does not publish or create native binaries.\n'
    printf 'Options: CLIENT_PORT=8081 CLIENT_HOST=lan; VISUAL or EDITOR selects the configuration editor.\n'
}

run_action() {
    case "$1" in
        1|build) build_client ;;
        2|rebuild) rebuild_client ;;
        3|start) start_client ;;
        4|clean) clean_client ;;
        5|configure) configure_client ;;
        6|install) install_dependencies ;;
        7|check) check_client ;;
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
    printf '\n=== WordRecall client ===\n'
    printf '1) Build web\n2) Rebuild web (fresh dependencies, clear bundler cache)\n3) Start development server\n4) Clean generated output\n5) Configure options\n6) Install dependencies\n7) Run checks and tests\n0) Exit\n'
    read -r -p 'Select operation: ' choice || break
    [[ "$choice" == 0 ]] && break
    if run_action "$choice"; then
        printf 'Operation completed.\n'
    else
        printf 'Operation failed or was cancelled; see the message above.\n' >&2
    fi
done
