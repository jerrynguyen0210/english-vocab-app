> **Existing production site:** Do not rerun this legacy installer. Follow `WORDRECALL_JETSON_PRODUCTION_MANUAL.md`, then publish the tested build with `bash devops/publish_production_web.sh`. The installer now refuses existing deployments to preserve the API proxy.

# English Vocabulary App — Jetson Nano web deployment

This guide deploys the **static web frontend** of an Expo / React Native application onto an ARM64 Jetson running Debian/Ubuntu. It exposes the web UI at **https://vocab.jerryitdev.com** through an existing or new Cloudflare Tunnel.

> Scope: This does **not** deploy a FastAPI/Node backend, PostgreSQL, Expo Router server functions, native iOS/Android apps, or other runtime API services. The actual repository could not be inspected when this installer was prepared, so confirm that the project is an Expo app and that static web export is supported. `expo.web.output = "server"` requires a different architecture.

## Installation after cloning

1. SSH into Jetson Nano as a normal user with `sudo` permission (do not run the script as root).
2. Clone the project and enter its directory:

   ```bash
   git clone https://github.com/jerrynguyen0210/english-vocab-app.git
   cd english-vocab-app
   ```

3. Copy `scripts/deploy-jetson.sh` and this documentation into the clone if they are not yet committed.
4. Run:

   ```bash
   chmod +x scripts/deploy-jetson.sh
   bash scripts/deploy-jetson.sh
   ```

   To select a nested Expo app, use `bash scripts/deploy-jetson.sh --app-dir apps/mobile` (replace the example with its actual directory).

### What is automated

- Validates ARM64 Debian/Ubuntu, repository and sudo access.
- Installs OS dependencies and Nginx; preserves all existing Nginx sites and listeners. On a fresh Nginx installation, disables the newly-created default port-80 site.
- Uses compatible system Node.js (22+) or downloads a verified Node 22 ARM64 release into the current user's application-specific directory, **without modifying system Node.js** (important for existing OpenClaw services).
- Runs `npm ci` from an npm lockfile (or `npm install` when none exists).
- Builds Expo Web with `expo export --platform web`.
- Checks for a static `index.html`; server-rendered output is intentionally rejected.
- Copies the build into `/srv/english-vocab-app/releases/...` and atomically changes `/srv/english-vocab-app/current`.
- Writes only its managed `/etc/nginx/sites-available/english-vocab-app.conf`, listening on `127.0.0.1:8088`.
- Reloads Nginx and checks the local HTTP endpoint.
- Installs Cloudflare's `cloudflared` package **only if absent**. An existing `cloudflared.service` is left unchanged.

### Cloudflare: one-time hostname setup

Open the [Cloudflare dashboard](https://dash.cloudflare.com/), select **Networking → Tunnels** and choose the tunnel connected to the Jetson. For an already-running tunnel, reuse it (no second service needed).

Create a **Published application** route:

| Field | Value |
|---|---|
| Subdomain | `vocab` |
| Domain | `jerryitdev.com` |
| Path | empty |
| Service type | HTTP |
| Service URL | `http://localhost:8088` |

Cloudflare manages the tunnel route and DNS. The public hostname should be `https://vocab.jerryitdev.com` once the tunnel is healthy and DNS has propagated.

If a tunnel does not yet exist, create one in the dashboard. The installer can provision the first `cloudflared` system service from a one-time tunnel token provided in a **local private file**:

```bash
mkdir -p "$HOME/.config/vocab"
chmod 700 "$HOME/.config/vocab"
umask 077
read -rsp 'Paste Cloudflare tunnel token: ' CF_TOKEN; echo
printf '%s' "$CF_TOKEN" > "$HOME/.config/vocab/tunnel-token"
unset CF_TOKEN
bash scripts/deploy-jetson.sh --tunnel-token-file "$HOME/.config/vocab/tunnel-token"
```

Use the **token string** from Cloudflare (not the entire installation command). Never commit a tunnel token or `.env` secret to Git. For a server with `cloudflared.service` already present, the token option does not replace the existing service. To exclude Cloudflare package installation entirely, run with `--skip-cloudflared`.

The dashboard route configuration is still required; a token alone does not create `vocab.jerryitdev.com`.

## Verify and operate

```bash
curl -I http://127.0.0.1:8088/
sudo nginx -t
sudo systemctl status nginx
sudo systemctl status cloudflared
curl -I https://vocab.jerryitdev.com/
```

To update after pushing commits:

```bash
cd english-vocab-app
git pull --ff-only
bash scripts/deploy-jetson.sh
```

If deployment changes port, update the Cloudflare published application's Service URL to match.

Useful troubleshooting:

```bash
journalctl -u nginx -n 100 --no-pager
journalctl -u cloudflared -n 100 --no-pager
ls -lah /srv/english-vocab-app/current
nginx -t
```

### Roll back a deployment

The script keeps earlier release folders, allowing manual rollback:

```bash
ls -1 /srv/english-vocab-app/releases
# Replace <previous-release> with a real folder name shown above.
sudo ln -sfn /srv/english-vocab-app/releases/<previous-release> /srv/english-vocab-app/.current-rollback
sudo mv -Tf /srv/english-vocab-app/.current-rollback /srv/english-vocab-app/current
sudo systemctl reload nginx
```

## Key considerations

- This is a **web-only static deployment**. Frontend code needing a backend should call a separately deployed HTTPS API. Do not put access tokens or database credentials into `EXPO_PUBLIC_*`; these values are embedded in browser code.
- Some Expo Router export modes produce multiple static pages, while server/API route modes need a Node.js service. This installer checks for `index.html` but cannot prove every route works. Test deep links and reload navigation before production use.
- The Jetson must remain powered on with internet access; the tunnel is outbound, requiring no router port forwarding.
- The app itself listens only on 127.0.0.1:8088. Fresh Nginx packages may briefly start a default port-80 site during installation; the script disables that default site after a new install. Existing Nginx sites and existing Cloudflare services are preserved. Check available disk space and memory before attempting a large frontend build.
- Do not run against an application you have not reviewed: `npm ci` and Expo build scripts execute code from the repository and packages.

Official documentation: [Expo web export](https://docs.expo.dev/more/expo-cli/#exporting), [Cloudflare tunnels](https://developers.cloudflare.com/tunnel/get-started/), [Cloudflare downloads](https://developers.cloudflare.com/tunnel/downloads/).
