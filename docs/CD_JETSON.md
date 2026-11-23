# Automatic deployment to the Jetson Nano

Every push to `main` runs the backend, client and deployment checks, builds the
production web SPA on GitHub, then deploys that exact commit to the Jetson over
SSH. Pull requests and pushes to other branches run checks without deployment.
The **CI and Jetson deployment** workflow also supports **Run workflow** on
`main` to retry a failed deployment. Older commits are rejected if `main` has
already moved.

The existing Backend and Client workflow files are now reusable checks called
by the combined workflow. If branch protection requires the previous check
names, update its required checks to the names shown by the combined workflow.

## 1. Prepare the board once

Follow [the Jetson deployment guide](DEPLOY_JETSON.md), retaining the existing
database, private `backend/.env`, Compose project, Nginx and Cloudflare tunnel.
Complete a successful manual deployment before enabling CD. CD updates the
existing installation; it does not configure a new Nginx site.

The deployment account needs:

- An existing checkout on branch `main`, with no tracked local changes. Use
  its absolute path below. Ignored files such as `backend/.env` are retained.
- Git access to `origin` without interactive prompts. For a private repository,
  configure a separate read-only GitHub deploy key on the board. The Actions
  checkout token is deliberately not transferred to the Jetson.
- Docker access without sudo, Compose v2 with `--wait`, ARM64, Python 3, curl,
  Nginx, tar, git and flock, as required by the deployment scripts.
- Noninteractive sudo for the existing deployment scripts' Nginx checks and
  release-file operations. Verify the account's sudo policy before using CD;
  the workflow never supplies a sudo password.

The board must be reachable from GitHub-hosted runners at the SSH address below.
An ordinary HTTP Cloudflare tunnel for the website does not by itself provide
this SSH connection. No board IP or website settings are changed by the workflow.

## 2. Set up SSH authentication

Generate a dedicated key on your own machine (outside this repository):

```bash
ssh-keygen -t ed25519 -f ~/.ssh/wordrecall_cd -C wordrecall-github-cd -N ''
```

Install the `.pub` key in the deployment user's `~/.ssh/authorized_keys` on the
Jetson. Keep the private key out of Git. This key authenticates Actions to the
Jetson; the board's GitHub deploy key, if needed, is separate.

Obtain the board's SSH host key using a trusted connection, and verify its
fingerprint on the board with:

```bash
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
```

From your machine, collect a known-hosts entry for the exact public SSH hostname
and port used by Actions, then compare its fingerprint with the trusted value:

```bash
ssh-keyscan -p 22 -t ed25519 YOUR_SSH_HOST > /tmp/wordrecall_known_hosts
ssh-keygen -lf /tmp/wordrecall_known_hosts
```

For a nonstandard port, use that port in `ssh-keyscan`; the entry will use
`[hostname]:port`. Save the verified entry as the secret below. CD enforces
host-key verification and never trusts a key collected during deployment.

## 3. Configure GitHub

In the repository, open **Settings → Environments**, create
`jetson-production`, and restrict its deployment branches to `main`. Leave
required reviewers disabled if you want fully automatic deployment.

Add these **environment secrets**:

| Secret | Value |
| --- | --- |
| `JETSON_SSH_PRIVATE_KEY` | Complete dedicated private key, including its header/footer; no passphrase |
| `JETSON_SSH_KNOWN_HOSTS` | Verified known-hosts entry for the exact SSH host and port |

Under **Settings → Secrets and variables → Actions → Variables**, add these
**repository variables**. `JETSON_PUBLIC_DOMAIN` belongs here because both the
cloud build and deployment need the same value.

| Variable | Value/default |
| --- | --- |
| `JETSON_HOST` | Required: public SSH hostname or IPv4 address reachable from GitHub runners; no `https://` prefix |
| `JETSON_USER` | Required: existing board deployment user, e.g. `jjnano` |
| `JETSON_REPO_PATH` | Required: absolute path to the existing checkout, e.g. `/home/jjnano/english-vocab-app`; no `~` or spaces |
| `JETSON_SSH_PORT` | `22` |
| `JETSON_PUBLIC_DOMAIN` | `vocab.jerryitdev.com`; hostname only |
| `JETSON_WEB_PORT` | Existing loopback Nginx port, `8088` |
| `JETSON_API_PORT` | Existing loopback API port, `8001` |
| `JETSON_RELEASE_ROOT` | Existing frontend release root, `/srv/english-vocab-app` |
| `JETSON_SKIP_PUBLIC_CHECK` | `false`; set `true` if Cloudflare Access intentionally blocks unauthenticated public checks |

Keep backend secrets only in the existing private `backend/.env` on the board;
do not put them in Actions variables or the SPA. Sanitized templates remain in
`backend/.env.example` and `client/.env.example`.

## 4. Enable and verify

Commit and push these workflow changes to `main`, or use **Actions → CI and
Jetson deployment → Run workflow → main** after configuration. No GitHub settings,
secrets or board configuration are created automatically by these repository files.

Inspect the `deploy` job for the successful commit SHA, then open the website
and check sign-in and a review page. The board fetches the tested SHA and only
fast-forwards its checkout; it refuses local modifications, divergence and stale
runs. It never resets the checkout or cleans ignored configuration.

Only one deployment job runs at a time. New pushes do not cancel an active
migration. A board-side lock also rejects overlapping CD runs. Avoid running a
separate manual deployment while CD is running.

The workflow builds JavaScript on GitHub rather than requiring modern Node on
the Nano. Backend images are built natively on the board using the existing
Dockerfile. A slow Nano build can exceed the 60-minute deployment job timeout;
inspect board state before retrying an interrupted deployment.

## Failures and recovery

- **Missing configuration / SSH failure:** add the settings above, check routing,
  key authentication and the verified host key, then rerun the workflow on `main`.
- **Private repository fetch failure:** fix the board's noninteractive GitHub
  access. GitHub Actions' SSH key only authorizes access to the board.
- **Dirty or divergent checkout:** preserve and resolve the board's local changes
  yourself. CD refuses to discard them.
- **Stale run:** use the workflow for the latest `main` commit.
- **Backend or migration failure:** inspect the API logs and persistent migration
  backups using the production Compose file. Workers may remain stopped until
  API startup succeeds. Fix forward, push, then deploy the new commit.
- **Frontend check failure:** the existing publisher restores the previous
  frontend link on local-check failure. A public-check failure after local
  success keeps the verified local release active and reports failure.

There is no automatic backend or database rollback. Schema migrations stay
forward-only, and database volumes and production secrets are preserved. A failed
deployment may already have fast-forwarded the board checkout; rerunning the
same current `main` commit is supported.

Workflow structure follows GitHub's [reusable workflow documentation](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows).
