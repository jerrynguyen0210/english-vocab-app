#!/usr/bin/env bash
# Atomically publish a prebuilt SPA without changing Nginx, DNS or the tunnel.
set -Eeuo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
build="$repo/client/dist"
root=/srv/english-vocab-app
domain=vocab.jerryitdev.com
port=8088
backend_port=8001
skip_public=0
allow_initial=0

usage() {
  printf 'Usage: bash devops/publish_production_web.sh [--build-dir PATH] [--domain HOST] [--port PORT] [--backend-port PORT] [--release-root PATH] [--skip-public-check] [--allow-initial]\n'
}
die() { printf '[publish] %s\n' "$*" >&2; exit 1; }
while (($#)); do
  case "$1" in
    --build-dir|--domain|--port|--backend-port|--release-root)
      (($# >= 2)) && [[ -n "$2" ]] || die "Missing value for $1"
      case "$1" in
        --build-dir) build=$2 ;; --domain) domain=$2 ;; --port) port=$2 ;;
        --backend-port) backend_port=$2 ;; --release-root) root=$2 ;;
      esac
      shift 2 ;;
    --skip-public-check) skip_public=1; shift ;;
    --allow-initial) allow_initial=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown option: $1" ;;
  esac
done
[[ "$domain" =~ ^[a-zA-Z0-9]([a-zA-Z0-9.-]*[a-zA-Z0-9])?$ ]] || die 'Invalid domain'
for number in "$port" "$backend_port"; do
  [[ "$number" =~ ^[0-9]{1,5}$ ]] && ((10#$number >= 1024 && 10#$number <= 65535)) || die 'Invalid port'
done
[[ "$root" == /* && "$root" != / ]] || die 'Release root must be an absolute directory other than /'
[[ -s "$build/index.html" && ! -d "$build/server" ]] || die 'Expected SPA output with index.html at its root. Build with WORDRECALL_WEB_OUTPUT=single.'
for command in curl cmp sudo git python3; do command -v "$command" >/dev/null || die "Required command: $command"; done
# Reject a mistakenly selected source tree or linked files outside the export.
python3 - "$build" <<'PY'
from pathlib import Path
import sys
root = Path(sys.argv[1]).resolve()
for path in root.rglob('*'):
    if path.is_symlink() or path.name.startswith('.env') or path.name in {'package.json', 'pyproject.toml'}:
        sys.exit('Refusing to publish source/configuration files or symlinks; select the SPA export directory.')
PY
sudo -v
[[ ! -e "$root/current" || -L "$root/current" ]] || die 'Current release is a directory; refusing to overwrite it'
if [[ ! -L "$root/current" && "$allow_initial" != 1 ]]; then
  die 'No existing release link. Use --allow-initial only for a new site.'
fi
curl -fsS --max-time 10 "http://127.0.0.1:$backend_port/health" >/dev/null || die 'Backend health check failed; website unchanged'
[[ $(curl -sS -o /dev/null -w '%{http_code}' --max-time 10 "http://127.0.0.1:$port/api/v1/auth/me") == 401 ]] || die 'Nginx /api/v1 proxy must return 401 for unauthenticated /auth/me; website unchanged'
sudo nginx -t
revision=$(git -C "$repo" rev-parse --short HEAD)
release="$root/releases/$(date -u +%Y%m%dT%H%M%SZ)-$revision-$$"
previous=''
if [[ -L "$root/current" ]]; then previous=$(readlink -f "$root/current"); fi
switched=0
rollback() {
  local status=$?
  if ((status != 0 && switched == 1)); then
    if [[ -n "$previous" ]]; then
      sudo ln -sfn -- "$previous" "$root/.current-rollback"
      sudo mv -Tf -- "$root/.current-rollback" "$root/current"
      printf 'Local check failed; previous frontend restored.\n' >&2
    else
      sudo rm -f -- "$root/current"
    fi
  fi
}
trap rollback EXIT
sudo install -d -m 0755 "$root/releases" "$release"
sudo cp -a -- "$build/." "$release/"
sudo chmod -R a+rX "$release"
sudo ln -sfn -- "$release" "$root/.current-next"
sudo mv -Tf -- "$root/.current-next" "$root/current"
switched=1
for route in / /review-preparation /sign-in; do
  curl -fsS --max-time 15 "http://127.0.0.1:$port$route" | cmp -s - "$build/index.html" || die "Local page check failed: $route"
done
[[ $(curl -sS -o /dev/null -w '%{http_code}' --max-time 10 "http://127.0.0.1:$port/api/v1/auth/me") == 401 ]] || die 'API proxy failed after publishing'
switched=0
printf 'Published: %s\nPrevious: %s\n' "$release" "${previous:-none}"
if ((skip_public == 0)); then
  if ! curl -fsS --max-time 20 -H 'Cache-Control: no-cache' "https://$domain/?release=$(basename "$release")" | cmp -s - "$build/index.html"; then
    die 'Local publication succeeded; public HTML could not be verified. Check Cloudflare Access/cache. The local release remains active.'
  fi
  [[ $(curl -sS -o /dev/null -w '%{http_code}' --max-time 20 "https://$domain/api/v1/auth/me") == 401 ]] || die 'Local publication succeeded; public API did not return 401. Check tunnel routing or Cloudflare Access.'
  printf 'Public website and API checks passed: https://%s\n' "$domain"
else
  printf 'Public checks skipped; local website and API checks passed.\n'
fi
