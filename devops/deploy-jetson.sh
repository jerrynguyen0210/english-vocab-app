#!/usr/bin/env bash
# Deploy this repository on the Jetson while retaining the existing public route.
set -Eeuo pipefail
REPO_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
DOMAIN=vocab.jerryitdev.com
PORT=8088
API_PORT=8001
WEB_BUILD_DIR=''
BUILD_DIR=''
CONFIGURE_NGINX=0
SKIP_BACKEND=0
SKIP_PUBLIC=0
BASE_DIR=/srv/english-vocab-app
SITE_FILE=/etc/nginx/sites-available/english-vocab-app.conf
SITE_LINK=/etc/nginx/sites-enabled/english-vocab-app.conf
COMPOSE_FILE="$REPO_ROOT/backend/docker-compose.jetson.yml"

log() { printf '\n[jetson] %s\n' "$*"; }
die() { printf '\n[error] %s\n' "$*" >&2; exit 1; }
cleanup() { if [[ -n "$BUILD_DIR" && -d "$BUILD_DIR" ]]; then rm -rf -- "$BUILD_DIR"; fi; }
trap cleanup EXIT
usage() {
  cat <<'EOF'
Usage: bash devops/deploy-jetson.sh [options]

Run on the Jetson from this repository. Existing Nginx and Cloudflare routing
are preserved by default. Backend images and the frontend release are updated.

  --web-build-dir PATH    Use an already-built SPA (recommended for older Jetsons)
  --domain HOST           Existing public hostname (default: vocab.jerryitdev.com)
  --port PORT             Existing loopback Nginx port (default: 8088)
  --backend-port PORT     Loopback API port (default: 8001)
  --release-root PATH     Existing web release directory (default: /srv/english-vocab-app)
  --configure-nginx       Explicitly install/update this app's managed Nginx site
  --skip-backend          Publish frontend against an already-running backend
  --skip-public-check     Validate locally only (e.g. Cloudflare Access blocks curl)
  --skip-cloudflared      Compatibility option; tunnels are always left unchanged
  -h, --help              Show help

Without --web-build-dir, Node 24+ and npm are required on the Jetson to build.
No OS packages, Node installation, tunnel configuration or DNS are changed.
EOF
}
while (($#)); do
  case "$1" in
    --web-build-dir|--domain|--port|--backend-port|--release-root)
      (($# >= 2)) && [[ -n "$2" ]] || die "Missing value for $1"
      case "$1" in
        --web-build-dir) WEB_BUILD_DIR=$2 ;; --domain) DOMAIN=$2 ;;
        --port) PORT=$2 ;; --backend-port) API_PORT=$2 ;;
        --release-root) BASE_DIR=$2 ;;
      esac
      shift 2 ;;
    --configure-nginx) CONFIGURE_NGINX=1; shift ;;
    --skip-backend) SKIP_BACKEND=1; shift ;;
    --skip-public-check) SKIP_PUBLIC=1; shift ;;
    --skip-cloudflared) shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown option: $1 (see --help)" ;;
  esac
done
[[ "$DOMAIN" =~ ^[a-zA-Z0-9]([a-zA-Z0-9.-]*[a-zA-Z0-9])?$ ]] || die 'Invalid public hostname'
[[ "$BASE_DIR" =~ ^/[a-zA-Z0-9_./-]+$ && "$BASE_DIR" != / ]] || die 'Release directory must be an absolute path without spaces'
for port in "$PORT" "$API_PORT"; do
  [[ "$port" =~ ^[0-9]{1,5}$ ]] && ((10#$port >= 1024 && 10#$port <= 65535)) || die 'Ports must be in 1024..65535'
done
[[ "$PORT" != "$API_PORT" ]] || die 'Nginx and API must use different ports'
[[ $(uname -m) == aarch64 ]] || die 'Run deployment on the ARM64 Jetson; build the SPA on another machine if needed'
((EUID != 0)) || die 'Run as the normal Jetson user, using sudo for Nginx and release files'
for command in sudo curl python3 nginx git; do command -v "$command" >/dev/null || die "Required command: $command"; done
sudo -v
sudo nginx -t
if ((CONFIGURE_NGINX == 0)); then
  [[ -L "$BASE_DIR/current" ]] || die 'No existing release symlink. Locate the working release root, or use --configure-nginx for a new managed site.'
else
  if sudo test -e "$SITE_FILE" && ! sudo grep -q 'managed-by: english-vocab-app-jetson' "$SITE_FILE"; then
    die "$SITE_FILE is not managed by this app; preserve it and configure the proxy manually"
  fi
  if [[ -e "$SITE_LINK" || -L "$SITE_LINK" ]]; then
    [[ $(readlink -f "$SITE_LINK") == "$SITE_FILE" ]] || die 'Nginx site link belongs to another configuration'
  elif command -v ss >/dev/null && [[ -n $(ss -H -ltn "sport = :$PORT") ]]; then
    die "Port $PORT is already used by an unmanaged site; use its existing proxy instead"
  fi
fi

export PUBLIC_DOMAIN="$DOMAIN" API_PORT
if ((SKIP_BACKEND == 0)); then
  command -v docker >/dev/null || die 'Install a working Docker Engine and Compose v2 before deployment'
  docker compose version >/dev/null || die 'Docker Compose v2 is required'
  [[ -f "$REPO_ROOT/backend/.env" ]] || die 'Configure backend/.env privately before deployment; see docs/DEPLOY_JETSON.md'
  docker compose --project-directory "$REPO_ROOT/backend" -f "$COMPOSE_FILE" config --quiet
  # Do not accidentally point a working website at a new empty database when an
  # existing API is managed by another Compose project or by systemd.
  api_id=$(docker compose --project-directory "$REPO_ROOT/backend" -f "$COMPOSE_FILE" ps -q api)
  if [[ -z "$api_id" ]] && command -v ss >/dev/null && [[ -n $(ss -H -ltn "sport = :$API_PORT") ]]; then
    die 'The API port belongs to another deployment. Match its Compose project/data configuration before proceeding, or use --skip-backend.'
  fi
  db_id=$(docker compose --project-directory "$REPO_ROOT/backend" -f "$COMPOSE_FILE" ps -a -q db)
  if [[ -n "$db_id" ]]; then
    expected_volume=$(docker compose --project-directory "$REPO_ROOT/backend" -f "$COMPOSE_FILE" config --format json | \
      python3 -c 'import json,sys; print(json.load(sys.stdin)["volumes"]["postgres_data"]["name"])')
    current_volume=$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/var/lib/postgresql/data"}}{{.Name}}{{end}}{{end}}' "$db_id")
    [[ -n "$current_volume" && "$current_volume" == "$expected_volume" ]] || die 'Database storage differs from the production definition. Set POSTGRES_VOLUME_NAME to the existing named volume, or explicitly preserve the existing bind mount; no update was performed.'
  elif command -v ss >/dev/null && [[ -n $(ss -H -ltn 'sport = :5432') ]]; then
    die 'An existing unmanaged PostgreSQL listener was found. Match its data configuration before starting a new database.'
  fi
fi

if [[ -n "$WEB_BUILD_DIR" ]]; then
  [[ -s "$WEB_BUILD_DIR/index.html" && ! -d "$WEB_BUILD_DIR/server" ]] || die 'Prebuilt directory must contain SPA index.html, not Expo server output'
  WEB_BUILD_DIR=$(cd -- "$WEB_BUILD_DIR" && pwd -P)
else
  command -v node >/dev/null && command -v npm >/dev/null || die 'Use --web-build-dir or install a compatible Node 24+ runtime'
  node -e 'const [major, minor] = process.versions.node.split(".").map(Number); if (!((major === 24 && minor >= 3) || major >= 26)) process.exit(1)' || die 'Use Node 24.3+ / 26+, or build the SPA on the Pi/laptop and pass --web-build-dir'
  BUILD_DIR=$(mktemp -d)
  log "Building SPA for https://$DOMAIN using the repository lockfile"
  (
    cd -- "$REPO_ROOT/client"
    npm ci --include=dev --no-audit --no-fund
    WORDRECALL_WEB_OUTPUT=single \
    EXPO_NO_DOTENV=1 \
    EXPO_PUBLIC_API_BASE_URL="https://$DOMAIN" \
    EXPO_PUBLIC_WEB_API_BASE_URL="https://$DOMAIN" \
      node node_modules/expo/bin/cli export --platform web --output-dir "$BUILD_DIR"
  )
  WEB_BUILD_DIR="$BUILD_DIR"
  [[ -s "$WEB_BUILD_DIR/index.html" ]] || die 'SPA export failed; current website was not changed'
fi

if ((SKIP_BACKEND == 0)); then
  log 'Building and starting production API, PostgreSQL and prompt worker'
  BACKEND_COMPOSE_FILE="$COMPOSE_FILE" bash "$REPO_ROOT/devops/deploy_backend.sh" start
fi
curl -fsS --max-time 10 "http://127.0.0.1:$API_PORT/health" >/dev/null || die 'Backend is not healthy; current website was not published'

if ((CONFIGURE_NGINX == 1)); then
  log 'Updating only this app’s explicitly selected Nginx site'
  config=$(mktemp)
  backup=$(mktemp)
  had_config=0
  had_link=0
  if sudo test -e "$SITE_FILE"; then sudo cat "$SITE_FILE" > "$backup"; had_config=1; fi
  if [[ -L "$SITE_LINK" ]]; then had_link=1; fi
  cat > "$config" <<EOF
# managed-by: english-vocab-app-jetson
server {
    listen 127.0.0.1:$PORT;
    server_name $DOMAIN localhost;
    root $BASE_DIR/current;
    index index.html;
    autoindex off;
    add_header X-Content-Type-Options nosniff always;
    # Cloudflared reaches this listener over loopback and supplies this header.
    set_real_ip_from 127.0.0.1;
    real_ip_header CF-Connecting-IP;

    location /api/ {
        proxy_pass http://127.0.0.1:$API_PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Forwarded-For \$remote_addr;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 60s;
    }
    location = /health {
        proxy_pass http://127.0.0.1:$API_PORT;
    }
    location = /index.html {
        add_header Cache-Control "no-store";
    }
    location / {
        add_header Cache-Control "no-cache";
        try_files \$uri \$uri/ /index.html;
    }
    location ~ /\\.(?!well-known) { deny all; }
}
EOF
  if ! sudo install -m 0644 "$config" "$SITE_FILE" || \
     ! sudo ln -sfn "$SITE_FILE" "$SITE_LINK" || \
     ! sudo nginx -t || ! sudo systemctl reload nginx; then
    if ((had_config)); then sudo install -m 0644 "$backup" "$SITE_FILE"; else sudo rm -f "$SITE_FILE"; fi
    if ((had_link == 0)); then sudo rm -f "$SITE_LINK"; fi
    sudo nginx -t && sudo systemctl reload nginx || true
    rm -f "$config" "$backup"
    die 'Nginx update failed; previous site configuration restored'
  fi
  rm -f "$config" "$backup"
fi

publish_options=(--build-dir "$WEB_BUILD_DIR" --domain "$DOMAIN" --port "$PORT" --backend-port "$API_PORT" --release-root "$BASE_DIR")
if ((SKIP_PUBLIC)); then publish_options+=(--skip-public-check); fi
if ((CONFIGURE_NGINX)) && [[ ! -L "$BASE_DIR/current" ]]; then publish_options+=(--allow-initial); fi
bash "$REPO_ROOT/devops/publish_production_web.sh" "${publish_options[@]}"
log "Deployment finished: https://$DOMAIN (existing Cloudflare tunnel and DNS retained)"
