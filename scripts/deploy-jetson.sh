#!/usr/bin/env bash
# Managed deployment for an Expo / React Native Web frontend on Debian/Ubuntu ARM64.
# Designed to coexist with existing Jetson services (including OpenClaw).
set -Eeuo pipefail

APP_NAME='english-vocab-app'
DOMAIN='vocab.jerryitdev.com'
PORT='8088'
SKIP_CLOUDFLARED=0
APP_DIR_INPUT=''
TUNNEL_TOKEN_FILE=''
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
BASE_DIR='/srv/english-vocab-app'
SITE_FILE='/etc/nginx/sites-available/english-vocab-app.conf'
SITE_LINK='/etc/nginx/sites-enabled/english-vocab-app.conf'
NODE_HOME="${HOME}/.local/share/english-vocab-app/node22"
BUILD_DIR=''

log()  { printf '\n[deploy] %s\n' "$*"; }
warn() { printf '\n[warning] %s\n' "$*" >&2; }
die()  { printf '\n[error] %s\n' "$*" >&2; exit 1; }
cleanup() { if [[ -n "$BUILD_DIR" && -d "$BUILD_DIR" ]]; then rm -rf -- "$BUILD_DIR"; fi; }
trap cleanup EXIT
trap 'warn "Failed at line $LINENO. Existing services have not been intentionally stopped."' ERR

usage() {
  cat <<'EOF'
Usage: bash scripts/deploy-jetson.sh [options]

Run after cloning this repository onto an ARM64 Ubuntu/Debian Jetson.

Options:
  --app-dir PATH          Path to Expo app relative to repository root (auto-detect otherwise)
  --domain HOSTNAME       Public hostname (default: vocab.jerryitdev.com)
  --port PORT             Local Nginx port (default: 8088; loopback only)
  --tunnel-token-file P   Optional Cloudflare Tunnel token file (outside Git)
  --skip-cloudflared      Do not install or configure cloudflared
  -h, --help              Show this help

Examples:
  bash scripts/deploy-jetson.sh
  bash scripts/deploy-jetson.sh --app-dir apps/mobile
  bash scripts/deploy-jetson.sh --tunnel-token-file "$HOME/.config/vocab/tunnel-token"

Notes:
  - Installs Nginx and uses a dedicated loopback port; does not change ports 80/443.
  - Installs Node 22 only under your home directory if needed; does not replace system Node.
  - Publishes only static Expo Web output. A backend/database must be deployed separately.
  - Cloudflare Published Application hostname routing is configured once in the dashboard.
EOF
}

while (( $# > 0 )); do
  case "$1" in
    --app-dir|--domain|--port|--tunnel-token-file)
      [[ $# -ge 2 && -n "$2" ]] || die "Missing value for $1"
      case "$1" in
        --app-dir) APP_DIR_INPUT="$2" ;;
        --domain) DOMAIN="$2" ;;
        --port) PORT="$2" ;;
        --tunnel-token-file) TUNNEL_TOKEN_FILE="$2" ;;
      esac
      shift 2 ;;
    --skip-cloudflared) SKIP_CLOUDFLARED=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown argument: $1 (see --help)" ;;
  esac
done

if [[ -e "$BASE_DIR/current" || -L "$BASE_DIR/current" ]]; then
  die 'Existing production deployment: use devops/publish_production_web.sh after building. This legacy installer must not overwrite the API proxy.'
fi

[[ "$PORT" =~ ^[0-9]+$ ]] || die 'Port must be numeric'
(( 1024 <= 10#$PORT && 10#$PORT <= 65535 )) || die 'Port must be in 1024..65535'
[[ "$DOMAIN" =~ ^[a-zA-Z0-9.-]+$ ]] || die 'Hostname contains invalid characters'
[[ "$(uname -m)" == 'aarch64' ]] || die 'This script targets Jetson ARM64 (uname -m must be aarch64)'
[[ -f /etc/debian_version ]] || die 'This script supports Debian/Ubuntu using apt'
[[ $EUID -ne 0 ]] || die 'Run as your normal SSH user (not as root); sudo is used where needed'
command -v sudo >/dev/null || die 'sudo is required'
command -v git >/dev/null || die 'git is required; clone this repository first'
sudo -v || die 'This user needs sudo permission'

log "Repository: $REPO_ROOT"
log 'Installing OS prerequisites (does not install/upgrade system Node.js)'
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y ca-certificates curl xz-utils
if ! command -v nginx >/dev/null 2>&1; then
  log 'Installing Nginx (new installations will not keep the default public site enabled)'
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y nginx
  # Only a newly-installed, package-created default site is disabled. Never remove
  # the default site of an existing Nginx installation used by other apps.
  if sudo test -L /etc/nginx/sites-enabled/default && \
     [[ "$(sudo readlink -f /etc/nginx/sites-enabled/default)" == '/etc/nginx/sites-available/default' ]]; then
    sudo rm /etc/nginx/sites-enabled/default
  fi
else
  log 'Nginx already exists; keeping its existing sites and listeners unchanged'
fi

ensure_node() {
  # Prioritize our isolated installation, then a compatible pre-existing Node.
  if [[ -x "$NODE_HOME/bin/node" ]]; then
    export PATH="$NODE_HOME/bin:$PATH"
  fi
  local major='0'
  if command -v node >/dev/null 2>&1; then
    major="$(node -p 'process.versions.node.split(".")[0]')"
  fi
  if (( major >= 22 )); then
    log "Using Node $(node --version) at $(command -v node)"
    return
  fi

  log 'Installing isolated Node.js 22 (ARM64), without changing OpenClaw/system Node'
  local tmp filename sum
  tmp="$(mktemp -d)"
  # SHASUMS256 is obtained from nodejs.org and used to validate the tarball.
  curl -fsSL 'https://nodejs.org/dist/latest-v22.x/SHASUMS256.txt' -o "$tmp/SHASUMS256.txt"
  filename="$(awk '$2 ~ /^node-v22\.[0-9.]+-linux-arm64\.tar\.xz$/ { print $2; exit }' "$tmp/SHASUMS256.txt")"
  [[ -n "$filename" ]] || die 'Unable to locate Node 22 ARM64 release archive'
  curl -fsSL "https://nodejs.org/dist/latest-v22.x/$filename" -o "$tmp/$filename"
  (cd "$tmp" && grep -F "  $filename" SHASUMS256.txt | sha256sum -c -)
  mkdir -p "$(dirname "$NODE_HOME")"
  mkdir -p "$tmp/node"
  tar -xJf "$tmp/$filename" -C "$tmp/node" --strip-components=1
  # Node is installed only under this app's per-user directory.
  if [[ -e "$NODE_HOME" ]]; then
    die "Node destination already exists but is unusable: $NODE_HOME"
  fi
  mv "$tmp/node" "$NODE_HOME"
  rm -rf "$tmp"
  export PATH="$NODE_HOME/bin:$PATH"
  log "Installed Node $(node --version)"
}
ensure_node
command -v npm >/dev/null || die 'npm was not found alongside Node.js'

is_expo_app() {
  [[ -f "$1/package.json" ]] && grep -Eq '"expo"[[:space:]]*:' "$1/package.json"
}

if [[ -n "$APP_DIR_INPUT" ]]; then
  [[ -d "$REPO_ROOT/$APP_DIR_INPUT" ]] || die "App path not found: $APP_DIR_INPUT"
  APP_DIR="$(cd "$REPO_ROOT/$APP_DIR_INPUT" && pwd -P)"
  case "$APP_DIR/" in "$REPO_ROOT/"*) ;; *) die '--app-dir must be inside the repository' ;; esac
  is_expo_app "$APP_DIR" || die "Not an Expo package: $APP_DIR/package.json"
else
  mapfile -d '' -t package_files < <(find "$REPO_ROOT" -maxdepth 5 -name package.json \
    -not -path '*/node_modules/*' -not -path '*/.git/*' -print0)
  apps=()
  for f in "${package_files[@]}"; do
    dir="$(dirname "$f")"
    if is_expo_app "$dir"; then apps+=("$dir"); fi
  done
  if (( ${#apps[@]} == 0 )); then
    die 'No Expo app found. Check the repo or provide --app-dir (this script needs Expo Web).'
  elif (( ${#apps[@]} > 1 )); then
    printf '%s\n' "${apps[@]}" >&2
    die 'More than one Expo app found; specify --app-dir'
  fi
  APP_DIR="${apps[0]}"
fi
log "Expo app: $APP_DIR"

# Install from the appropriate lockfile. Do not overwrite dependency versions.
if [[ -f "$APP_DIR/package-lock.json" || -f "$APP_DIR/npm-shrinkwrap.json" ]]; then
  (cd "$APP_DIR" && npm ci --include=dev --no-audit --no-fund)
elif [[ "$APP_DIR" != "$REPO_ROOT" && -f "$REPO_ROOT/package-lock.json" ]]; then
  (cd "$REPO_ROOT" && npm ci --include=dev --no-audit --no-fund)
elif [[ -f "$APP_DIR/pnpm-lock.yaml" || -f "$APP_DIR/yarn.lock" \
  || -f "$REPO_ROOT/pnpm-lock.yaml" || -f "$REPO_ROOT/yarn.lock" ]]; then
  die 'A pnpm/yarn lockfile was detected. Use the matching package manager or adapt the installer.'
else
  warn 'No npm lockfile found: npm install will generate a lockfile locally'
  (cd "$APP_DIR" && npm install --include=dev --no-audit --no-fund)
fi

[[ -x "$APP_DIR/node_modules/.bin/expo" || -x "$REPO_ROOT/node_modules/.bin/expo" ]] \
  || die 'Expo CLI is not installed. Check package.json and npm installation.'

BUILD_DIR="$(mktemp -d)"
log 'Exporting production web frontend'
(cd "$APP_DIR" && npx --no-install expo export --platform web --output-dir "$BUILD_DIR")
[[ -f "$BUILD_DIR/index.html" ]] || die \
  'Build has no index.html. Check Expo web output: static/SPA is supported; server/API output is not.'

log 'Installing versioned static release'
release="${BASE_DIR}/releases/$(date -u +%Y%m%dT%H%M%SZ)-$$"
sudo install -d -m 0755 "$BASE_DIR/releases" "$release"
sudo cp -a "$BUILD_DIR/." "$release/"
sudo chmod -R a+rX "$release"
if sudo test -e "$BASE_DIR/current" && ! sudo test -L "$BASE_DIR/current"; then
  die "$BASE_DIR/current exists and is not a symlink; refusing to overwrite it"
fi
old_target=''
if sudo test -L "$BASE_DIR/current"; then
  old_target="$(sudo readlink "$BASE_DIR/current")"
fi

log 'Configuring an isolated Nginx listener on loopback'
if sudo test -e "$SITE_FILE" && ! sudo grep -q 'managed-by: english-vocab-app-jetson' "$SITE_FILE"; then
  die "$SITE_FILE already exists and is not managed by this script; refusing to replace it"
fi
if ! sudo test -e "$SITE_FILE" && command -v ss >/dev/null 2>&1; then
  if ss -H -ltn "sport = :$PORT" | grep -q .; then
    die "Port $PORT is already in use. Supply --port with an unused local port."
  fi
fi
nginx_config="$(mktemp)"
cat > "$nginx_config" <<EOF
# managed-by: english-vocab-app-jetson
server {
    listen 127.0.0.1:$PORT;
    server_name localhost;
    root $BASE_DIR/current;
    index index.html;
    autoindex off;

    add_header X-Content-Type-Options nosniff always;

    location / {
        try_files \$uri \$uri/ /index.html;
    }

    location ~ /\\.(?!well-known) {
        deny all;
    }
}
EOF
sudo install -m 0644 "$nginx_config" "$SITE_FILE"
rm -f "$nginx_config"
if sudo test -e "$SITE_LINK" || sudo test -L "$SITE_LINK"; then
  [[ "$(sudo readlink -f "$SITE_LINK")" == "$SITE_FILE" ]] || \
    die "$SITE_LINK is in use by another site; refusing to replace its link"
fi
sudo ln -sfn "$SITE_FILE" "$SITE_LINK"
sudo nginx -t || die 'Nginx syntax check failed; check the site configuration before retrying'

# Switch release via atomic rename; preserve the previous target for rollback.
sudo ln -sfn "$release" "$BASE_DIR/.current-next"
sudo mv -Tf "$BASE_DIR/.current-next" "$BASE_DIR/current"
sudo systemctl enable --now nginx
sudo systemctl reload nginx
if ! curl -fsS --max-time 10 "http://127.0.0.1:$PORT/" -o /dev/null; then
  warn 'New release health check failed; attempting to restore previous release'
  if [[ -n "$old_target" ]]; then
    sudo ln -sfn "$old_target" "$BASE_DIR/.current-rollback"
    sudo mv -Tf "$BASE_DIR/.current-rollback" "$BASE_DIR/current"
    sudo systemctl reload nginx || true
  fi
  die 'Local HTTP health check failed (check journalctl -u nginx)'
fi
log "Local frontend passed health check: http://127.0.0.1:$PORT/"

if (( SKIP_CLOUDFLARED == 0 )); then
  if ! command -v cloudflared >/dev/null 2>&1; then
    log 'Installing cloudflared, without modifying an existing tunnel'
    sudo install -d -m 0755 /usr/share/keyrings
    curl -fsSL 'https://pkg.cloudflare.com/cloudflare-main.gpg' \
      | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
    echo 'deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main' \
      | sudo tee /etc/apt/sources.list.d/cloudflared.list >/dev/null
    sudo apt-get update
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y cloudflared
  fi

  if systemctl cat cloudflared.service >/dev/null 2>&1; then
    log 'Existing cloudflared service detected. Leaving it unchanged.'
  elif [[ -n "$TUNNEL_TOKEN_FILE" ]]; then
    [[ -r "$TUNNEL_TOKEN_FILE" && -s "$TUNNEL_TOKEN_FILE" ]] \
      || die 'Tunnel token file not found/readable (must not be inside Git)'
    log 'Installing new cloudflared service from token file'
    tunnel_token="$(tr -d '\r\n' < "$TUNNEL_TOKEN_FILE")"
    [[ -n "$tunnel_token" ]] || die 'Tunnel token file was empty'
    sudo cloudflared service install "$tunnel_token"
    unset tunnel_token
    sudo systemctl enable --now cloudflared
  else
    warn 'Cloudflared is installed but no service was configured; see Cloudflare Dashboard instructions.'
  fi
fi

printf '\n=== DEPLOYMENT SUMMARY ===\n'
printf 'Expo app:       %s\n' "$APP_DIR"
printf 'Static release: %s\n' "$release"
printf 'Local URL:      http://127.0.0.1:%s/\n' "$PORT"
printf 'Public URL:     https://%s/ (after Cloudflare route configured)\n' "$DOMAIN"
printf '\nCloudflare route: %s -> http://localhost:%s\n' "$DOMAIN" "$PORT"
printf 'Update: git pull --ff-only && bash scripts/deploy-jetson.sh\n'
printf 'See docs/DEPLOY_JETSON.md for first-time tunnel/route setup.\n'
