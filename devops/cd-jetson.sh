#!/usr/bin/env bash
# GitHub runner side: transfer the SPA and deploy an exact, tested commit.
set -Eeuo pipefail

die() { printf '[cd] %s\n' "$*" >&2; exit 1; }
[[ $# == 2 ]] || die 'Usage: bash devops/cd-jetson.sh COMMIT_SHA SPA_DIRECTORY'
revision=$1
build=$2
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
[[ "$revision" =~ ^[a-f0-9]{40}$ ]] || die 'Expected a full Git commit SHA'
[[ -s "$build/index.html" && ! -d "$build/server" ]] || die 'Expected a prebuilt SPA'
for name in JETSON_HOST JETSON_USER JETSON_REPO_PATH JETSON_SSH_PRIVATE_KEY JETSON_SSH_KNOWN_HOSTS; do
  [[ -n "${!name:-}" ]] || die "Configure $name in GitHub Actions first (see docs/CD_JETSON.md)"
done
[[ "$JETSON_HOST" =~ ^[a-zA-Z0-9][a-zA-Z0-9.-]*$ ]] || die 'Expected an IPv4 address or SSH hostname'
[[ "$JETSON_USER" =~ ^[a-zA-Z_][a-zA-Z0-9_-]*$ ]] || die 'Invalid SSH username'
[[ "$JETSON_REPO_PATH" =~ ^/[a-zA-Z0-9_./-]+$ ]] || die 'Repository path must be absolute, without spaces (expand ~ yourself)'
port=${JETSON_SSH_PORT:-22}
if [[ ! "$port" =~ ^[0-9]{1,5}$ ]]; then die 'Invalid SSH port'; fi
if ((10#$port < 1 || 10#$port > 65535)); then die 'Invalid SSH port'; fi

umask 077
temp=$(mktemp -d)
remote_temp=''
cleanup() {
  status=$?
  trap - EXIT
  if [[ -n "$remote_temp" ]]; then
    "${ssh_cmd[@]}" "rm -rf -- '$remote_temp'" || true
  fi
  rm -rf -- "$temp"
  exit "$status"
}
trap cleanup EXIT
printf '%s\n' "$JETSON_SSH_PRIVATE_KEY" > "$temp/key"
printf '%s\n' "$JETSON_SSH_KNOWN_HOSTS" > "$temp/known_hosts"
unset JETSON_SSH_PRIVATE_KEY JETSON_SSH_KNOWN_HOSTS
options=(-i "$temp/key" -o IdentitiesOnly=yes -o BatchMode=yes
  -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$temp/known_hosts"
  -o ConnectTimeout=15 -o ServerAliveInterval=15 -o ServerAliveCountMax=4)
target="$JETSON_USER@$JETSON_HOST"
ssh_cmd=(ssh "${options[@]}" -p "$port" "$target")
remote_temp=$("${ssh_cmd[@]}" 'umask 077; mktemp -d /tmp/wordrecall-cd.XXXXXXXXXX')
[[ "$remote_temp" =~ ^/tmp/wordrecall-cd\.[a-zA-Z0-9_-]+$ ]] || { remote_temp=''; die 'Unexpected remote temporary path'; }
tar -C "$build" -czf "$temp/web.tar.gz" .
scp "${options[@]}" -P "$port" "$temp/web.tar.gz" "$target:$remote_temp/web.tar.gz"
# Quote arguments for the remote login shell; never interpolate configuration
# directly into executable SSH command text.
printf -v command 'bash -s -- %q ' "$JETSON_REPO_PATH"
printf -v arguments '%q ' "$revision" "$remote_temp" \
  "${JETSON_PUBLIC_DOMAIN:-vocab.jerryitdev.com}" "${JETSON_WEB_PORT:-8088}" \
  "${JETSON_API_PORT:-8001}" "${JETSON_RELEASE_ROOT:-/srv/english-vocab-app}" \
  "${JETSON_SKIP_PUBLIC_CHECK:-false}"
"${ssh_cmd[@]}" "$command$arguments" < "$repo/devops/cd-jetson-remote.sh"
