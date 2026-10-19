# Deploy relay to Hetzner

Deployment checklist for the single-node Talos cluster. Commands assume the
repo root.

## Before you start

- [ ] Make sure that `hcloud`, `aws`, `jq`, `gh`, `dotenvx`, `envsubst`,
  `openssl`, `dig`, `kubectl`, `python3` and `go` are installed.
- [ ] Install `talosctl` (`TALOS_VERSION`, `v1.14.2`):
  ```bash
  brew tap siderolabs/tap
  brew install siderolabs/tap/talosctl@1.14
  brew link --force siderolabs/tap/talosctl@1.14
  ```
- [ ] Install `hcloud-upload-image` (`v1.5.0`):
  ```bash
  go install github.com/apricote/hcloud-upload-image@v1.5.0
  ```
- [ ] Create the Hetzner context:
  ```bash
  HCLOUD_TOKEN="<token>" hcloud context create relay --token-from-env
  export HCLOUD_TOKEN="<token>"
  ```
- [ ] Restore `.env.keys` in the repo root. The file is git-ignored, so get
  it from your backup.
- [ ] Export Object Storage credentials for the first run:
  ```bash
  export AWS_ACCESS_KEY_ID="<key>"
  export AWS_SECRET_ACCESS_KEY="<secret>"
  ```
- [ ] Open outbound ports 25 and 465 in the Hetzner Console. Mail delivery
  fails without them.

## Provision

- [ ] Run `RELAY_HOSTNAME="relays.to" ./deploy/provision.sh`.
- [ ] Add the printed nameservers to the registrar.
- [ ] Rerun `./deploy/provision.sh`.

## OAuth credentials

- [ ] Create the GitHub app with callback
  `https://relays.to/social/github/login/callback/`.
- [ ] Store the credentials:
  ```bash
  dotenvx set GITHUB_CLIENT_ID "<id>" -f .env.production
  dotenvx set GITHUB_CLIENT_SECRET "<secret>" -f .env.production
  ```
- [ ] Commit and push `.env.production` to `main`:
  ```bash
  git add .env.production && git commit -m "Add OAuth credentials" && git push
  ```

## Deploy

- [ ] Dispatch the deploy from `main`: `gh workflow run deploy.yml --ref main`.

## Verify

- [ ] `curl https://relays.to/health/node/` answers 200.
- [ ] `curl https://relays.to/health/application/` answers 200.
- [ ] `curl https://relays.to/health/pipeline/` answers 200. A failure can
  come from a third-party incident.
- [ ] `curl -i -X POST https://relays.to/mcp -d '{}'` answers 401 with a
  discovery pointer, not 502.
- [ ] `openssl s_client -connect smtp.relays.to:587 -starttls smtp` completes
  the TLS handshake.
- [ ] `openssl s_client -connect mx1.relays.to:25 -starttls smtp` completes the
  TLS handshake.
- [ ] `dig +short pg.relays.to storage.relays.to` answers with addresses.
- [ ] `export KUBECONFIG=deploy/.state/talos/kubeconfig && kubectl get pods`
  shows every pod `Running` with `1/1` ready, and every Job `Completed`.

## Rerun and inspect

- [ ] Run every step that is not done yet: `./deploy/provision.sh`.
- [ ] Run one step: `./deploy/provision.sh <step>`.
- [ ] Show what is done and what is pending: `./deploy/provision.sh --status`.
- [ ] List the steps in order: `./deploy/provision.sh --list`.

## Upgrades

- [ ] Upgrade by hand with `deploy/upgrade.sh`.
- [ ] Or trigger the workflow with `gh workflow run upgrade.yml`.
