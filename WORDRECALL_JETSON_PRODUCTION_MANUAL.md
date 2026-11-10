---
title: "WordRecall: Jetson Nano Production Deployment Manual"
subtitle: "Expo Web + FastAPI + PostgreSQL + Nginx + Cloudflare Tunnel"
date: "10 November 2026"
---

# WordRecall — Complete Production Deployment Manual

**Repository:** <https://github.com/jerrynguyen0210/english-vocab-app>

**Public URL:** <https://vocab.jerryitdev.com>

**Deployment:** Jetson Nano / Ubuntu ARM64 / Docker / Nginx / Cloudflare Tunnel
**Document version:** 1.0 — 10 November 2026

> **Scope and status.** This documents the installation that was configured and tested in the setup conversation, plus a repeatable procedure for a clean Jetson. The public web page returned HTTP 200, FastAPI returned HTTP 200 at its local health endpoint, and authenticated API endpoints returned the expected HTTP 401 when called without a token. The user subsequently reported the setup completed. Full registration, sign-in and database-persistence tests should still be performed after future releases. This is **web hosting**, not an App Store / Play Store native-app release.

---

## 1. What is deployed

```text
User browser (HTTPS)
    |
    v
vocab.jerryitdev.com (Cloudflare DNS + HTTPS)
    |
    v
Cloudflare Tunnel: jetson-vocab (healthy)
    |
    v
Jetson Nano 127.0.0.1:8088 (Nginx)
    |                               |
    | /                             | /api/*
    v                               v
Expo / React Native Web         FastAPI (Docker)
/srv/english-vocab-app/current  127.0.0.1:8001 -> container :8000
                                    |
                                    v
                              PostgreSQL 17 (Docker)
                              127.0.0.1:5432 -> container :5432
```

| Item | Verified / intended setting |
|---|---|
| App | WordRecall (English Vocabulary App) |
| Git repository | `jerrynguyen0210/english-vocab-app`, default branch `main` |
| Repository layout | `client/` (Expo SDK 58) and `backend/` (FastAPI) |
| Device OS | Ubuntu with Nginx 1.18.0 (observed); ARM64 check needed on fresh systems |
| Expo web output | `"single"` (one SPA `dist/index.html`) |
| Public hostname | `vocab.jerryitdev.com` |
| Cloudflare tunnel | `jetson-vocab` (healthy in setup) |
| Cloudflare published application | `https://vocab.jerryitdev.com` → `http://localhost:8088` |
| Nginx site | `/etc/nginx/sites-available/english-vocab-app.conf` |
| Nginx document root | `/srv/english-vocab-app/current` |
| Frontend listener | `127.0.0.1:8088` |
| FastAPI listener | `127.0.0.1:8001` on host; `8000` in container |
| PostgreSQL listener | `127.0.0.1:5432` on host; `5432` in container |
| Production Compose | `backend/compose.production.yaml` (locally created during setup; may not be committed) |
| Backend environment | `backend/.env` (private; never commit) |
| Frontend build environment | `client/.env.local` (public URLs only; never commit environment files) |

**Shell setup:** After opening a new SSH session, navigate to your actual repository location and run `export REPO_ROOT="$(git rev-parse --show-toplevel)"` before using commands in this guide that reference `$REPO_ROOT`.

**Important deployment rule:** the earlier `scripts/deploy-jetson.sh` installer was designed for **frontend-only** setup and may regenerate `/etc/nginx/sites-available/english-vocab-app.conf` without the `/api/` proxy. **Do not rerun that original script on the working production server** unless it has been updated to preserve the FastAPI proxy configuration. Use Section 9 to deploy frontend updates safely.

## 2. Prerequisites and safety checks

On a fresh Jetson, ensure you have:

- An ARM64 Ubuntu/Debian device with internet access and enough storage/memory for `npm ci`, Expo export and Docker builds.
- A user with `sudo` privileges; run application commands as that normal user, **not** with `sudo npm` or `sudo code`.
- Git, Python 3, Node.js **24** for this repository's current client requirements, npm, Docker Engine, Docker Compose, Nginx, and `cloudflared`.
- A Cloudflare account with `jerryitdev.com` active.
- Free localhost TCP ports `8088`, `8001`, and `5432`, or explicit replacements in all configurations.

Run checks:

```bash
uname -m                            # Usually aarch64 on Jetson
cat /etc/os-release
node --version                      # Node 24 for current repository
npm --version
docker --version
docker compose version
sudo systemctl is-active docker
sudo ss -lntp | grep -E ':(8088|8001|5432)\b' || true
```

**Existing production installation:** ports `8088`, `8001` and `5432` will be occupied by your own services; do not treat that as a problem. Do not change or remove existing OpenClaw containers, services or files. Avoid `docker system prune --volumes`, `docker compose down -v` and broad `docker rm` commands.

Install basic utilities if missing:

```bash
sudo apt update
sudo apt install -y git curl ca-certificates nginx rsync python3
```

Install Docker/Compose and Node 24 via their official distribution instructions if missing. Avoid replacing a Node runtime used by OpenClaw; a per-user Node version manager is preferable. Recheck `node --version` in the same shell used to build.

## 3. Clone and locate the project

On a fresh device:

```bash
git clone https://github.com/jerrynguyen0210/english-vocab-app.git
cd english-vocab-app
export REPO_ROOT="$(git rev-parse --show-toplevel)"
```

**Never assume the repo lives at `~/english-vocab-app`.** In the observed session, that guessed location did not exist. From anywhere inside a clone, determine its actual location:

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
printf 'Repository: %s\n' "$REPO_ROOT"
ls "$REPO_ROOT/client/app.json" "$REPO_ROOT/backend/docker-compose.yml"
```

Directory structure:

```text
english-vocab-app/
├── client/
│   ├── app.json
│   ├── package.json
│   ├── package-lock.json
│   ├── .env.local            # create locally; ignored by Git
│   └── dist/                 # generated web export
├── backend/
│   ├── Dockerfile
│   ├── entrypoint.sh
│   ├── docker-compose.yml    # development only
│   ├── compose.production.yaml  # create separately for production
│   └── .env                  # create locally; secret
└── docs/
```

## 4. Configure FastAPI and PostgreSQL for production

### 4.1. Preserve existing production data first

**On a fresh deployment only**, generate a new database password. On an existing deployment, **keep its current `POSTGRES_PASSWORD`**, even if you change other settings; the PostgreSQL data volume remembers the password assigned on initialization.

Inspect existing WordRecall volumes without deleting anything:

```bash
docker volume ls --format '{{.Name}}' | grep -E '(^|_)postgres_data$' || true
```

If the volume already exists, follow Section 10 (backup) before editing any database configuration.

### 4.2. Create production environment variables (fresh deployment)

From the repository root:

```bash
cd "$REPO_ROOT/backend"
if [ -f .env ]; then
  echo 'Existing backend/.env: preserve it and review manually.'
else
  cp .env.example .env
  chmod 600 .env
fi
```

**Run the next generator only when `.env` was newly created and no WordRecall database has been initialized.** On an existing system, leave the password and secret intact. Generate values and update the copied template without displaying passwords:

```bash
python3 - <<'PY'
from pathlib import Path
import json
import os
import secrets

path = Path('.env')
lines = path.read_text().splitlines()
settings = {
    'POSTGRES_USER': 'vocab',
    'POSTGRES_DB': 'vocab',
    'POSTGRES_PASSWORD': secrets.token_hex(24),
    'POSTGRES_PORT': '5432',
    'SECRET_KEY': secrets.token_urlsafe(48),
    'AUTH_COOKIE_SECURE': 'true',
    'CORS_ORIGINS': json.dumps(['https://vocab.jerryitdev.com']),
}
settings['DATABASE_URL'] = (
    f"postgresql+psycopg://{settings['POSTGRES_USER']}:"
    f"{settings['POSTGRES_PASSWORD']}@localhost:5432/"
    f"{settings['POSTGRES_DB']}"
)
updated, seen = [], set()
for line in lines:
    if '=' in line and not line.lstrip().startswith('#'):
        key = line.split('=', 1)[0].strip()
        if key in settings:
            if key not in seen:
                updated.append(f'{key}={settings[key]}')
                seen.add(key)
            continue
    updated.append(line)
for key, value in settings.items():
    if key not in seen:
        updated.append(f'{key}={value}')
path.write_text('\n'.join(updated) + '\n')
os.chmod(path, 0o600)
print('Production environment created without printing secrets.')
PY
```

This initializes: a random Postgres password, a random app secret, browser `Secure` cookies, and the exact CORS origin. The `DATABASE_URL` in `.env` is for commands run on the host; Compose supplies the container-internal `db` hostname to the API. The `EXPO_PUBLIC_*` values used later are **not secrets** and become part of web JavaScript.

For an **already running system**, do **not** repeat the new-secret generation. Confirm necessary fields exist, then preserve passwords. Keep `.env` backed up securely outside version control.

### 4.3. Create the standalone production Compose file

In `backend/compose.production.yaml`:

```yaml
name: wordrecall

services:
  db:
    image: postgres:17
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${POSTGRES_USER:?Missing POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?Missing POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB:?Missing POSTGRES_DB}
    ports:
      - "127.0.0.1:5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", 'pg_isready -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"']
      interval: 5s
      timeout: 5s
      retries: 15

  api:
    build: .
    restart: unless-stopped
    env_file:
      - .env
    environment:
      DATABASE_URL: postgresql+psycopg://${POSTGRES_USER:?Missing POSTGRES_USER}:${POSTGRES_PASSWORD:?Missing POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB:?Missing POSTGRES_DB}
      AUTH_COOKIE_SECURE: "true"
      CORS_ORIGINS: '["https://vocab.jerryitdev.com"]'
    ports:
      - "127.0.0.1:8001:8000"
    depends_on:
      db:
        condition: service_healthy
    command:
      - uvicorn
      - app.main:app
      - --host
      - 0.0.0.0
      - --port
      - "8000"

volumes:
  postgres_data:
```

**Why not `backend/docker-compose.yml`?** That existing file is for development: it includes code bind mounts, Uvicorn `--reload`, and exposes API port `8001` on `0.0.0.0`. The production file intentionally has no bind mounts or auto-reload and binds host ports to `127.0.0.1`.

Confirm configuration without printing secret-filled Compose output:

```bash
docker compose -f compose.production.yaml config --quiet \
  && echo 'Production Compose valid'
```

Verify host bindings (does not reveal credentials):

```bash
python3 - <<'PY'
import json
import subprocess
obj = json.loads(subprocess.check_output(
    ['docker', 'compose', '-f', 'compose.production.yaml',
     'config', '--format', 'json'], text=True))
for name in ('api', 'db'):
    for port in obj['services'][name].get('ports', []):
        print(f"{name}: {port.get('host_ip')}:{port.get('published')}"
              f" -> {port.get('target')}")
PY
```

Expected:

```text
api: 127.0.0.1:8001 -> 8000
db: 127.0.0.1:5432 -> 5432
```

### 4.4. Start the backend

```bash
cd "$REPO_ROOT/backend"
docker compose -f compose.production.yaml up -d --build
docker compose -f compose.production.yaml ps
curl -i --max-time 10 http://127.0.0.1:8001/health
```

Expected FastAPI health response:

```text
HTTP/1.1 200 OK
{"status":"ok"}
```

The repo's `backend/entrypoint.sh` runs `python -m app.migrate` **before** the API starts; the API container exits if migrations fail. `/health` confirms the API process is responsive, **not** end-to-end DB availability. Check PostgreSQL too:

```bash
docker compose -f compose.production.yaml exec -T db \
  sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

Look at logs if needed:

```bash
docker compose -f compose.production.yaml logs --tail=100 api db
```

## 5. Build the Expo Web frontend

### 5.1. Public API URLs

In `client/.env.local`, use these exact URLs for web production:

```dotenv
EXPO_PUBLIC_API_BASE_URL=https://vocab.jerryitdev.com
EXPO_PUBLIC_WEB_API_BASE_URL=https://vocab.jerryitdev.com
```

Do **not** append `/api/v1`; the client adds `/api/v1` itself. Web authentication uses an HttpOnly cookie and requires the API and web app to share the same HTTPS origin. Changing `.env.local` requires a **new build**; values are embedded in the exported JS.

For native iOS/Android builds, supply an appropriate production API URL at **native build time** too. Hosting the web bundle does not create installable phone apps.

### 5.2. Fix the Expo export mode

The current repository was found with:

```json
"web": {
  "output": "server",
  "favicon": "./assets/images/favicon.png"
}
```

For Nginx SPA hosting, the working setting is:

```json
"web": {
  "output": "single",
  "favicon": "./assets/images/favicon.png"
}
```

`server` mode creates Expo server/client output and does **not** have root-level `dist/index.html` for this hosting method. `single` creates `dist/index.html`. Keep the file valid JSON: **do not** add `//` comments. If a Git pull restores `"server"`, change it back to `"single"` before exporting. Ideally commit a reviewed production-appropriate setting to the repository.

Check:

```bash
cd "$REPO_ROOT/client"
python3 -m json.tool app.json > /dev/null && echo 'app.json valid'
python3 - <<'PY'
import json
from pathlib import Path
mode = json.loads(Path('app.json').read_text())['expo']['web']['output']
assert mode == 'single', f'Expected web.output="single", got {mode!r}'
print('Expo SPA mode: single')
PY
```

### 5.3. Install, export, validate

```bash
cd "$REPO_ROOT/client"
node --version                 # Expect Node 24
npm ci
npx expo export --platform web --output-dir dist
test -s dist/index.html && echo 'Expo web export successful'
ls -lh dist/index.html
du -sh dist
```

During the successful setup, Expo reported `Web Bundled` and `Exported: dist`; `dist/index.html` was about 1.6 KB. The index size is not itself a health check; most application code lives in `_expo/static/js/...` bundles.

## 6. Serve the web app and API with Nginx

This is the **intended combined Nginx configuration**, not the earlier frontend-only version. If the site already works, do not overwrite it unnecessarily; back up and compare first.

On a **fresh installation only**, create the web root and copy the initial build. If the root already exists, use the update/backup procedure in Section 9 instead:

```bash
if [ -e /srv/english-vocab-app/current ] || [ -L /srv/english-vocab-app/current ]; then
  echo 'Existing web deployment detected: use Section 9 instead.'
else
  sudo mkdir -p /srv/english-vocab-app/current
  sudo rsync -a "$REPO_ROOT/client/dist/" /srv/english-vocab-app/current/
fi
```

If `/srv/english-vocab-app/current` is an existing symlink to a **versioned release**, preserve that structure; never replace it with a regular directory.

Site path:

```text
/etc/nginx/sites-available/english-vocab-app.conf
```

Recommended combined server block:

```nginx
server {
    listen 127.0.0.1:8088;
    server_name localhost;
    root /srv/english-vocab-app/current;
    index index.html;
    autoindex off;

    add_header X-Content-Type-Options nosniff always;

    location ^~ /api/ {
        proxy_pass http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_connect_timeout 10s;
        proxy_read_timeout 60s;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }

    location ~ /\.(?!well-known) {
        deny all;
    }
}
```

`proxy_pass` deliberately has **no trailing slash**; FastAPI must receive `/api/v1/...` unchanged. Existing local setup already had both `location /` and `location ^~ /api/`. The prefix location wins for API requests irrespective of their order.

To set up on a new machine, activate the site without deleting unrelated sites:

```bash
sudo ln -sfn /etc/nginx/sites-available/english-vocab-app.conf \
  /etc/nginx/sites-enabled/english-vocab-app.conf
sudo nginx -t
sudo systemctl enable --now nginx
sudo systemctl reload nginx
```

Check local web and API:

```bash
curl -I http://127.0.0.1:8088/
curl -i http://127.0.0.1:8088/api/v1/auth/me
```

Expected results: **HTTP 200** with `text/html` for `/`, and **HTTP 401** with a JSON `Invalid or expired access token` message for `/api/v1/auth/me` without credentials. The `401` is the correct proof that your reverse proxy reached the protected API.

**About `/health`:** as currently configured, `https://vocab.jerryitdev.com/health` returns the Expo HTML page due to SPA fallback; it does **not** represent the FastAPI health endpoint. The authoritative local check is `http://127.0.0.1:8001/health`. If you want a public API health route, deliberately add `location = /health { proxy_pass http://127.0.0.1:8001/health; }` to Nginx and validate/reload. Do not infer backend health from an HTML response.

## 7. Publish with Cloudflare Tunnel

The working tunnel configured during setup was **`jetson-vocab`**, which Cloudflare showed as **Healthy** with one connector. If that tunnel already exists, **reuse it**; do not reinstall or create another `cloudflared` system service.

### 7.1. Create/connect a tunnel on a new server (one time)

1. Sign in to <https://dash.cloudflare.com/> and ensure `jerryitdev.com` is Active.
2. Open **Networking → Tunnels**.
3. Choose **Create Tunnel**, select **Cloudflared**, and name it `jetson-vocab`.
4. Follow Cloudflare's **Linux connector** installation instructions on the Jetson. These include a private token. **Never paste the token into a document, Git repository, screenshot or chat.**
5. Confirm the connector appears **Healthy** before routing traffic.

### 7.2. Configure the published application hostname

In **Networking → Tunnels → jetson-vocab → Routes → Add route → Published application**:

| Field | Value |
|---|---|
| Subdomain | `vocab` |
| Domain | `jerryitdev.com` |
| Path | blank |
| Service type | HTTP |
| Service URL | `http://localhost:8088` |

Save. Cloudflare normally associates the required DNS record with this published hostname. Do not forward router ports `80` or `443` for this tunnel-based deployment.

Verify:

```bash
sudo systemctl is-active cloudflared
curl -I https://vocab.jerryitdev.com
curl -i https://vocab.jerryitdev.com/api/v1/auth/me
```

Expected public responses: **HTTP/2 200** for `/`, **HTTP/2 401** for unauthenticated `/api/v1/auth/me`.

## 8. End-to-end acceptance checklist

The following checks were observed in the completed setup:

- [x] Local frontend `http://127.0.0.1:8088` returned `200 OK`.
- [x] Local FastAPI `http://127.0.0.1:8001/health` returned `{"status":"ok"}`.
- [x] API through Nginx `/api/v1/auth/me` returned `401 Unauthorized` without a token.
- [x] API through Cloudflare `/api/v1/auth/me` returned `401 Unauthorized` without a token.
- [x] Public `https://vocab.jerryitdev.com` returned `HTTP/2 200`.
- [x] Cloudflare tunnel dashboard reported **Healthy**.

Recommended browser checks for each new production release:

- [ ] Open the site in an incognito/private window; it renders the sign-in/sign-up interface.
- [ ] Register a new test user; verify the UI signs in successfully.
- [ ] Sign out, sign in, refresh the browser page and verify refresh-cookie session restoration.
- [ ] Add a vocabulary word, review it, refresh and confirm it remains saved.
- [ ] Verify a direct/deep URL works after browser refresh (SPA fallback).
- [ ] Confirm no mixed-content, CORS, cookie or JavaScript errors in browser developer tools.
- [ ] Confirm Docker Compose reports PostgreSQL healthy and FastAPI running.

**Security:** Never share actual login passwords, refresh tokens, `SECRET_KEY`, `POSTGRES_PASSWORD` or Cloudflare tunnel tokens when reporting logs/screenshots.

## 9. Safe redeployment after `git pull`

**This is the recommended update procedure for the current deployment.** It intentionally avoids rerunning the older frontend-only installer, which could remove Nginx's `/api/` block.

### 9.1. Check for local changes

```bash
cd "$REPO_ROOT"
git status --short
```

Because `client/app.json` may be edited locally and `backend/compose.production.yaml` may be untracked, `git pull --ff-only` can fail or overwrite intended configuration. Review those files before pulling. Do **not** blindly run `git reset --hard` or `git clean -fd`.

```bash
git pull --ff-only
```

If the pull refuses to proceed, resolve local tracked changes deliberately (commit, stash, or reconcile) rather than deleting them.

### 9.2. Backend updates (when backend code changed)

Take a database backup first (Section 10); schema migrations may run during startup:

```bash
cd "$REPO_ROOT/backend"
docker compose -f compose.production.yaml config --quiet
docker compose -f compose.production.yaml up -d --build
docker compose -f compose.production.yaml ps
curl -fsS http://127.0.0.1:8001/health
```

Migrations are forward-only; rolling back the API image does **not** automatically roll back a database schema. Always review migrations for compatibility before deployment.

### 9.3. Rebuild frontend with production API URL

```bash
cd "$REPO_ROOT/client"
grep '^EXPO_PUBLIC_.*API_BASE_URL=' .env.local
python3 -m json.tool app.json >/dev/null
npm ci
npx expo export --platform web --output-dir dist
test -s dist/index.html
```

Confirm `expo.web.output` is `"single"` before export. If output says `server`, adjust `client/app.json` as explained in Section 5, without JSON comments.

### 9.4. Publish without overwriting Nginx

In the **working installation**, `/srv/english-vocab-app/current` may be a release symlink. Two safe publishing choices follow. **Choose exactly one** after inspecting `ls -ld /srv/english-vocab-app/current`.

**Option A — current is a real directory:** back it up, then sync the web build only:

```bash
BACKUP="/srv/english-vocab-app/backups/web-$(date -u +%Y%m%dT%H%M%SZ)"
sudo mkdir -p "$BACKUP"
sudo rsync -a /srv/english-vocab-app/current/ "$BACKUP/"
sudo rsync -a --delete "$REPO_ROOT/client/dist/" \
  /srv/english-vocab-app/current/
```

**Option B — current is a symlink:** create a versioned release, then atomically repoint the symlink:

```bash
RELEASE="/srv/english-vocab-app/releases/$(date -u +%Y%m%dT%H%M%SZ)"
sudo mkdir -p "$RELEASE"
sudo rsync -a "$REPO_ROOT/client/dist/" "$RELEASE/"
sudo chmod -R a+rX "$RELEASE"
sudo ln -sfn "$RELEASE" /srv/english-vocab-app/.current-next
sudo mv -Tf /srv/english-vocab-app/.current-next \
  /srv/english-vocab-app/current
```

**Never sync `dist/` into a directory containing application source code, secrets, or persistent data.** Confirm the destination is strictly a static web root. These commands do **not** regenerate Nginx or touch your Docker database volume.

### 9.5. Validate after deployment

```bash
sudo nginx -t
curl -I http://127.0.0.1:8088/
curl -i http://127.0.0.1:8088/api/v1/auth/me
curl -I https://vocab.jerryitdev.com/
curl -i https://vocab.jerryitdev.com/api/v1/auth/me
```

A web update needs **no Nginx reload** when only static files change. If you edit `/etc/nginx/sites-available/english-vocab-app.conf`, then run `sudo nginx -t && sudo systemctl reload nginx`.

## 10. Backups, rollback and recovery

### 10.1. Database backups (priority)

Run from `backend/`; the database container must be running:

```bash
cd "$REPO_ROOT/backend"
umask 077
mkdir -p "$HOME/wordrecall-backups"
BACKUP="$HOME/wordrecall-backups/postgres-$(date -u +%Y%m%dT%H%M%SZ).sql.gz"
docker compose -f compose.production.yaml exec -T db \
  sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' \
  | gzip > "$BACKUP"
test -s "$BACKUP" && ls -lh "$BACKUP"
```

Store a copy **off the Jetson** (encrypted storage or another trusted machine). A backup only on the Jetson cannot protect against disk failure. Regularly test restores on a separate throwaway instance. The SQL archive may contain user information: treat it as confidential.

**Do not restore over an active production database using a one-liner.** A restore requires a maintenance window, a known-clean target database and a plan to reconcile running API processes and migrations.

### 10.2. Frontend rollback

If `current` is a symlink, list releases:

```bash
ls -l /srv/english-vocab-app/current
ls -1 /srv/english-vocab-app/releases
```

Choose a known-good release from the actual list, then:

```bash
PREVIOUS=/srv/english-vocab-app/releases/<existing-release-directory>
sudo ln -sfn "$PREVIOUS" /srv/english-vocab-app/.current-rollback
sudo mv -Tf /srv/english-vocab-app/.current-rollback \
  /srv/english-vocab-app/current
```

Replace `<existing-release-directory>` with a real directory name. For a regular-directory deployment, restore from a verified `/srv/english-vocab-app/backups/web-*` copy instead. Rollback only changes the frontend; it does not reverse database migrations.

### 10.3. Keep backups of operational files

Back up (securely) `backend/.env`, `backend/compose.production.yaml`, `client/.env.local`, the custom Nginx site file, and the Cloudflare tunnel configuration. Store secrets outside Git and limit permissions. Do not share `docker compose config` output publicly; it can include credentials.

## 11. Operational commands

| Goal | Command |
|---|---|
| Show API and DB containers | `docker compose -f backend/compose.production.yaml --project-directory backend ps` (from repo root; see note) |
| Backend health | `curl -fsS http://127.0.0.1:8001/health` |
| Web health | `curl -I http://127.0.0.1:8088/` |
| Public web | `curl -I https://vocab.jerryitdev.com/` |
| Protected API test | `curl -i https://vocab.jerryitdev.com/api/v1/auth/me` (401 without token) |
| Nginx config check | `sudo nginx -t` |
| Nginx logs | `sudo journalctl -u nginx -n 100 --no-pager` |
| Tunnel service | `sudo systemctl status cloudflared` |
| Tunnel logs | `sudo journalctl -u cloudflared -n 100 --no-pager` |

For Docker commands with greatest consistency, **change into `"$REPO_ROOT/backend"` first** and use `docker compose -f compose.production.yaml ...`. Examples:

```bash
cd "$REPO_ROOT/backend"
docker compose -f compose.production.yaml ps
docker compose -f compose.production.yaml logs --tail=100 api db
docker compose -f compose.production.yaml restart api
```

Do not edit live application code inside containers; rebuild the image. To stop WordRecall intentionally (without deleting data):

```bash
docker compose -f compose.production.yaml down
```

This stops WordRecall services and retains the named volume. **Never add `-v` during routine operations.**

## 12. Troubleshooting quick reference

| Symptom | Likely cause | Action |
|---|---|---|
| `Build has no index.html` | `expo.web.output` is `server` | Change to `single`, validate JSON, rebuild |
| `JSONDecodeError` near `web` setting | `//` comment or invalid JSON | Remove comments; `python3 -m json.tool client/app.json` |
| `curl :8001/health` connection refused | FastAPI container not running | `docker compose ... ps`, inspect API/DB logs |
| Browser shows `Unable to restore your session` | Compiled API URL wrong or backend unreachable | Verify `.env.local`, rebuild/redeploy, test public `/api/v1/auth/me` |
| Public `/api/v1/auth/me` returns HTML | Nginx lacks `/api/` proxy | Restore `location ^~ /api/` and reload |
| Public `/api/v1/auth/me` returns 401 | No bearer token sent | Expected connectivity result, not a network failure |
| Public `/health` returns HTML | SPA catch-all handles `/health` | Test local `:8001/health`; optionally add exact `/health` proxy |
| Cloudflare 502 / tunnel failure | Tunnel service unhealthy or Nginx listener unavailable | Check `cloudflared` and `curl -I http://127.0.0.1:8088` |
| App works locally, fails on public URL | Missing Cloudflare route/DNS, TLS or tunnel | Inspect `jetson-vocab` published hostname route |
| Cookies fail after login | Different origin, HTTP, stale web bundle or `AUTH_COOKIE_SECURE` | Use one HTTPS hostname; verify CORS and rebuild |
| `git pull` refuses | Local tracked edits (often `client/app.json`) | Review `git status`, reconcile intentionally |
| API works but database actions fail | DB, credentials or migration issue | Check `db` health, API logs and migration errors; preserve volume |
| API rate-limits many unrelated users | Proxy IP handling may group users behind tunnel | Review trusted-proxy configuration before production scale |
| Running old deploy script removes `/api/` | Script rewrites frontend-only Nginx site | Use Section 9 or update script to preserve proxy |

### Known constraints and future hardening

- The `cloudflared` tunnel presents a public site. Consider Cloudflare WAF rules, abuse monitoring and backups appropriate to your user base.
- Rate limiting behind a reverse proxy requires correctly handling **trusted** client IP headers. Do **not** blindly trust visitor-controlled `X-Forwarded-For` values; test how FastAPI identifies users via Cloudflare/Nginx before relying on per-IP limits.
- Nginx sends `X-Forwarded-Proto: https` because public users access Cloudflare over HTTPS while the private origin hop is HTTP. Verify the app's proxy/header handling before adding another intermediary.
- Restrict PostgreSQL and FastAPI to localhost on the Jetson (currently verified). Avoid opening ports 5432/8001 to the LAN or internet.
- The Expo SPA host supports client-side React Native Web routes, **not** Expo Router server functions/API routes. If server output becomes necessary, redesign hosting accordingly.
- Consider automated off-device PostgreSQL backups, release health checks, logging/alerting, and deployment script improvements as follow-up engineering work.

## 13. Fast checklist for a future reinstall

1. Verify device, dependencies, Git clone, `REPO_ROOT` and port availability.
2. Configure `backend/.env` securely and create the standalone `backend/compose.production.yaml`.
3. `docker compose -f compose.production.yaml up -d --build`; verify PostgreSQL and `127.0.0.1:8001/health`.
4. Set `client/.env.local` URLs to `https://vocab.jerryitdev.com`.
5. Set `client/app.json` → `expo.web.output: "single"`; validate JSON.
6. `npm ci`, `npx expo export --platform web --output-dir dist`; verify `dist/index.html`.
7. Publish to `/srv/english-vocab-app/current`; keep the `/api/` Nginx proxy.
8. Configure `jetson-vocab` Published application → `http://localhost:8088`.
9. Confirm public web 200, public protected API 401, then test registration, login and saved words.
10. Set up encrypted off-device backups and document rollback/releases.

---

## Official reference documentation

- [Expo: Publish websites](https://docs.expo.dev/guides/publishing-websites/) — `single`, `server`, `static`, and `dist` exports.
- [Cloudflare: Add a published application route](https://developers.cloudflare.com/cloudflare-one/networks/routes/add-routes/) — tunnel hostname and local origin.
- [Cloudflare: Create a dashboard-managed tunnel](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/get-started/create-remote-tunnel/).
- [Docker Compose CLI](https://docs.docker.com/compose/reference/) — `up`, `ps`, `logs`, `exec`, and configuration validation.
- [Nginx reverse proxy guide](https://docs.nginx.com/nginx/admin-guide/web-server/reverse-proxy/).

*Maintained for the WordRecall Jetson deployment. Update this manual whenever the domain, application routes, Compose project, or persistent data layout changes.*
