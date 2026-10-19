# Deploy relay to Hetzner

Deployment checklist for the single-node Talos cluster. Commands assume the
repo root.

## Before you start

- [ ] Install `talosctl` (`TALOS_VERSION`, `v1.14.2`).
- [ ] Install `hcloud-upload-image` (`v1.5.0`).
- [ ] Create the Hetzner context:
  ```bash
  HCLOUD_TOKEN="<token>" hcloud context create relay --token-from-env
  export HCLOUD_TOKEN="<token>"
  ```
- [ ] Restore `.env.keys` in the repo root.
- [ ] Export Object Storage credentials for the first run:
  ```bash
  export AWS_ACCESS_KEY_ID="<key>"
  export AWS_SECRET_ACCESS_KEY="<secret>"
  ```
- [ ] Open outbound ports 25 and 465.

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
- [ ] Commit and push `.env.production`:
  ```bash
  git add .env.production && git commit -m "Add OAuth credentials" && git push
  ```

## Deploy

- [ ] `gh workflow run deploy.yml` from `main`.

## Verify

- [ ] `curl https://relays.to/health/node/`
- [ ] `curl https://relays.to/health/application/`
- [ ] `curl https://relays.to/health/pipeline/`
- [ ] `curl -i -X POST https://relays.to/mcp -d '{}'`
- [ ] `openssl s_client -connect smtp.relays.to:587 -starttls smtp`
- [ ] `openssl s_client -connect mx1.relays.to:25 -starttls smtp`
- [ ] `dig +short pg.relays.to storage.relays.to`
- [ ] `export KUBECONFIG=deploy/.state/talos/kubeconfig && kubectl get pods`

## Rerun and inspect

- [ ] `./deploy/provision.sh`
- [ ] `./deploy/provision.sh <step>`
- [ ] `./deploy/provision.sh --status`
- [ ] `./deploy/provision.sh --list`

## Upgrades

- [ ] `deploy/upgrade.sh`
- [ ] Or `gh workflow run upgrade.yml`
