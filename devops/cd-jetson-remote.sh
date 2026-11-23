#!/usr/bin/env bash
# Executed on the Jetson by cd-jetson.sh; not an interactive setup script.
set -Eeuo pipefail
die() { printf '[cd-remote] %s\n' "$*" >&2; exit 1; }
[[ $# == 8 ]] || die 'Expected repository, SHA, upload directory, domain, web/API ports, release root, public-check flag'
repo=$1 revision=$2 upload=$3 domain=$4 web_port=$5 api_port=$6 release_root=$7 skip_public=$8
[[ "$revision" =~ ^[a-f0-9]{40}$ ]] || die 'Invalid commit SHA'
[[ "$upload" =~ ^/tmp/wordrecall-cd\.[a-zA-Z0-9_-]+$ && -s "$upload/web.tar.gz" ]] || die 'Missing SPA upload'
[[ "$skip_public" == true || "$skip_public" == false ]] || die 'JETSON_SKIP_PUBLIC_CHECK must be true or false'
export GIT_TERMINAL_PROMPT=0
for command in git flock sudo tar; do command -v "$command" >/dev/null || die "Required command: $command"; done
mkdir -p "$HOME/.local/state/english-vocab-app"
exec 9>"$HOME/.local/state/english-vocab-app/deploy.lock"
flock -n 9 || die 'Another deployment is running on this board'
cd -- "$repo"
[[ $(git rev-parse --show-toplevel) == "$(pwd -P)" ]] || die 'Select the root of the existing checkout'
[[ $(git symbolic-ref --short HEAD) == main ]] || die 'Existing checkout must be on main'
[[ -z $(git status --porcelain --untracked-files=no) ]] || die 'Tracked local changes exist; preserve/resolve them before deploying'
[[ -f backend/.env ]] || die 'Configure the existing private backend/.env first'
sudo -n true || die 'Deployment requires noninteractive sudo for the existing Jetson deploy scripts'
# Skip obsolete runs after newer pushes. Never deploy untested branch-tip code.
latest=$(git ls-remote --exit-code origin refs/heads/main | cut -f1)
[[ "$latest" == "$revision" ]] || die 'This run is stale: main has moved; deploy the newer workflow run'
git fetch --no-tags origin "$revision"
git merge-base --is-ancestor HEAD "$revision" || die 'Checkout has diverged or is newer; refusing to reset it'
git merge --ff-only "$revision"
[[ $(git rev-parse HEAD) == "$revision" ]] || die 'Checkout does not match the tested commit'
mkdir "$upload/web"
tar -xzf "$upload/web.tar.gz" -C "$upload/web" --no-same-owner --no-same-permissions
options=(--web-build-dir "$upload/web" --domain "$domain" --port "$web_port"
  --backend-port "$api_port" --release-root "$release_root")
if [[ "$skip_public" == true ]]; then options+=(--skip-public-check); fi
bash devops/deploy-jetson.sh "${options[@]}"
printf '[cd-remote] Successfully deployed %s\n' "$revision"
