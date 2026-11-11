#!/usr/bin/env bash
# Publish an already-built SPA; preserve Nginx, API, database and prior release.
set -Eeuo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
build="$repo/client/dist"
root=/srv/english-vocab-app
[[ -s "$build/index.html" ]] || { echo 'Build client/dist first.' >&2; exit 1; }
[[ -L "$root/current" ]] || { echo 'Expected existing release symlink; refusing to replace a directory.' >&2; exit 1; }
curl -fsS --max-time 10 http://127.0.0.1:8001/health >/dev/null
[[ $(curl -sS -o /dev/null -w '%{http_code}' --max-time 10 http://127.0.0.1:8088/api/v1/auth/me) == 401 ]]
release="$root/releases/$(date -u +%Y%m%dT%H%M%SZ)-$(git -C "$repo" rev-parse --short HEAD)"
previous=$(readlink -f "$root/current")
sudo -v
sudo nginx -t
sudo mkdir -- "$release"
sudo rsync -a -- "$build/" "$release/"
sudo chmod -R a+rX "$release"
sudo ln -sfn -- "$release" "$root/.current-next"
sudo mv -Tf -- "$root/.current-next" "$root/current"
if ! curl -fsS --max-time 15 http://127.0.0.1:8088/review-preparation | cmp -s - "$build/index.html"; then
    sudo ln -sfn -- "$previous" "$root/.current-rollback"
    sudo mv -Tf -- "$root/.current-rollback" "$root/current"
    echo 'Local release check failed; previous frontend restored.' >&2
    exit 1
fi
printf 'Published: %s\nPrevious: %s\n' "$release" "$previous"
curl -fsS --max-time 20 https://vocab.jerryitdev.com/ | cmp -s - "$build/index.html" || {
    echo 'Local release passed; public HTML differs. Check Cloudflare caching.' >&2
    exit 1
}
echo 'Public website matches the new build.'
