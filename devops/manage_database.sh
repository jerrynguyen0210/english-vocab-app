#!/usr/bin/env bash
set -uo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd) || exit 1
BACKEND_DIR=$(cd -- "$SCRIPT_DIR/../backend" && pwd) || exit 1

database_sql() {
    local target=$1
    shift
    command -v docker >/dev/null 2>&1 || {
        printf 'Docker is required.\n' >&2
        return 1
    }
    docker compose version >/dev/null 2>&1 || {
        printf 'Docker Compose v2 or later is required.\n' >&2
        return 1
    }
    if [[ ! -f "$BACKEND_DIR/.env" ]]; then
        printf 'Backend configuration is missing. Run deploy_backend.sh configure first.\n' >&2
        return 1
    fi
    (
        cd -- "$BACKEND_DIR" || exit 1
        docker compose --project-directory "$BACKEND_DIR" -f "$BACKEND_DIR/docker-compose.yml" \
            exec -T db sh -c '
                export PGPASSWORD="${POSTGRES_PASSWORD:-}"
                exec psql -X --no-password --username "${POSTGRES_USER:-postgres}" \
                    --set ON_ERROR_STOP=1 --pset pager=off "$@"
            ' sh --dbname "$target" "$@"
    )
}

read_name() {
    local variable=$1 prompt=$2 value
    read -r -p "$prompt" value || return 1
    if [[ ! "$value" =~ ^[a-zA-Z_][a-zA-Z0-9_-]{0,62}$ ]]; then
        printf 'Use 1–63 ASCII letters, digits, underscores or hyphens; start with a letter or underscore.\n' >&2
        return 1
    fi
    printf -v "$variable" '%s' "$value"
}

allow_change() {
    case "$1" in
        postgres|template0|template1)
            printf 'System database %s is protected by this helper.\n' "$1" >&2
            return 1
            ;;
    esac
}

confirm_change() {
    local expected=$1 answer
    read -r -p "Type $expected to confirm: " answer || return 1
    [[ "$answer" == "$expected" ]] || {
        printf 'Operation cancelled.\n' >&2
        return 1
    }
}

list_databases() {
    database_sql postgres <<'SQL'
SELECT datname AS database,
       pg_get_userbyid(datdba) AS owner,
       pg_encoding_to_char(encoding) AS encoding,
       pg_size_pretty(pg_database_size(oid)) AS size,
       datconnlimit AS connection_limit,
       CASE WHEN datname IN ('postgres', 'template0', 'template1')
            THEN 'protected' ELSE '' END AS management
FROM pg_database
ORDER BY datname;
SQL
}

view_database() {
    local database
    read_name database 'Database to inspect: ' || return
    database_sql "$database" --set "database=$database" <<'SQL'
SELECT datname AS database,
       pg_get_userbyid(datdba) AS owner,
       pg_encoding_to_char(encoding) AS encoding,
       pg_size_pretty(pg_database_size(oid)) AS size,
       datconnlimit AS connection_limit
FROM pg_database WHERE datname = :'database';
SELECT table_schema AS schema, table_name AS name, table_type AS type
FROM information_schema.tables
WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
ORDER BY table_schema, table_name;
SQL
}

create_database() {
    local database
    read_name database 'New database name: ' || return
    allow_change "$database" || return
    database_sql postgres --set "database=$database" <<'SQL' || return
CREATE DATABASE :"database";
SQL
    printf 'Created %s. Application tables and migrations are not installed automatically.\n' "$database"
}

rename_database() {
    local database new_name
    read_name database 'Database to rename: ' || return
    allow_change "$database" || return
    read_name new_name 'New database name: ' || return
    allow_change "$new_name" || return
    if [[ "$database" == "$new_name" ]]; then
        printf 'The new name must be different.\n' >&2
        return 1
    fi
    printf 'Renaming %s to %s changes its connection name. Stop dependent services and update their configuration afterwards.\n' "$database" "$new_name"
    confirm_change "RENAME $database TO $new_name" || return
    database_sql postgres --set "database=$database" --set "new_name=$new_name" <<'SQL'
ALTER DATABASE :"database" RENAME TO :"new_name";
SQL
}

change_owner() {
    local database owner
    read_name database 'Database to edit: ' || return
    allow_change "$database" || return
    read_name owner 'Existing PostgreSQL role for the new owner: ' || return
    printf 'This changes database ownership only; existing table ownership and grants are unchanged.\n'
    confirm_change "OWNER $database TO $owner" || return
    database_sql postgres --set "database=$database" --set "owner=$owner" <<'SQL'
ALTER DATABASE :"database" OWNER TO :"owner";
SQL
}

edit_database() {
    local choice
    printf '\n1) Rename database\n2) Change database owner\n0) Back\n'
    read -r -p 'Select edit: ' choice || return 1
    case "$choice" in
        1) rename_database ;;
        2) change_owner ;;
        0) return 0 ;;
        *) printf 'Unknown edit choice.\n' >&2; return 2 ;;
    esac
}

clear_table_data() {
    local database schema table
    read_name database 'Database containing the table: ' || return
    allow_change "$database" || return
    read_name schema 'Schema name (usually public): ' || return
    read_name table 'Table to clear: ' || return
    case "$schema" in
        pg_*|information_schema)
            printf 'System schemas cannot be cleared.\n' >&2
            return 1
            ;;
    esac
    if [[ "$table" == alembic_version ]]; then
        printf 'Migration history cannot be cleared.\n' >&2
        return 1
    fi
    database_sql "$database" --set "schema=$schema" --set "table=$table" <<'SQL' || return
SELECT count(*) AS current_row_count FROM :"schema".:"table";
SQL
    printf 'Clear all data in %s.%s.%s? The database, table structure and identity sequences are kept.\n' "$database" "$schema" "$table"
    printf 'Related tables will not be cleared automatically. Foreign-key restrictions and history protections still apply.\n'
    confirm_change "CLEAR $database.$schema.$table" || return
    database_sql "$database" --set "schema=$schema" --set "table=$table" <<'SQL' || return
BEGIN;
SET LOCAL lock_timeout = '5s';
TRUNCATE TABLE :"schema".:"table" CONTINUE IDENTITY RESTRICT;
COMMIT;
SQL
    printf 'Table data cleared; structure preserved.\n'
}

usage() {
    printf 'Usage: %s [list|view|create|edit|clear|--help]\n' "$0"
    printf 'No argument opens the menu. Connects to the existing backend Compose db service; start it first.\n'
    printf 'Manages databases, lists tables and clears selected table data; never drops databases or tables.\n'
    printf 'Clear keeps identity sequences and refuses cascading deletion; migration history and system schemas are protected.\n'
    printf 'Names use 1–63 ASCII letters, digits, underscores or hyphens, starting with a letter or underscore.\n'
}

run_action() {
    case "$1" in
        1|list) list_databases ;;
        2|view) view_database ;;
        3|create|add) create_database ;;
        4|edit) edit_database ;;
        5|clear) clear_table_data ;;
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
    printf '\n=== WordRecall database management (existing Compose PostgreSQL) ===\n'
    printf '1) List databases\n2) View database details and tables\n3) Add database\n4) Edit database (rename / owner)\n5) Clear table data (keep structure)\n0) Exit\n'
    read -r -p 'Select operation: ' choice || break
    [[ "$choice" == 0 ]] && break
    if run_action "$choice"; then
        printf 'Operation completed.\n'
    else
        printf 'Operation failed or was cancelled. Check the message above and that the db service is running.\n' >&2
    fi
done
