# Deploy relay to Hetzner

One script, one server. It stops wherever it needs you, and rerunning the same
command carries on from there.

The server runs a single-node k3s cluster. This guide covers provisioning and
day-to-day operations; the deployment's internals live in `deploy/k8s/`.

## Before you start

Install nothing. `hcloud`, `aws`, `jq`, `gh`, `dotenvx`, `envsubst`,
`ssh-keygen` and `dig` are already on this machine.

Three things to have ready:

1. **A Hetzner token**, in hcloud:

   ```bash
   HCLOUD_TOKEN="<token>" hcloud context create relay --token-from-env
   ```

2. **`.env.keys`** in the repo root. It decrypts the committed
   `.env.production` and is git-ignored, so restore it from wherever you keep
   it.

3. **Object Storage credentials**, on the first provisioning only. Later runs
   read them from `.env.production`, where they are stored as
   `AWS_S3_ACCESS_KEY_ID` and `AWS_S3_SECRET_ACCESS_KEY`, the names
   django-storages uses:

   ```bash
   export AWS_ACCESS_KEY_ID="<key>"
   export AWS_SECRET_ACCESS_KEY="<secret>"
   ```

Then open outbound ports 25 and 465 in the Console. Everything works without
them except mail delivery.

## 1. Provision

If a server named `relays.to` already exists, reinstall it first. That includes
the box an earlier Compose deployment ran on. `user_data` applies at first boot
only, so a run that finds an existing server reuses it as-is and never installs
k3s, and the environment step then waits for a cluster that is not there. See
[Reinstalling the server](#reinstalling-the-server).

```bash
RELAY_HOSTNAME="relays.to" \
    SSH_PUBLIC_KEY_FILES="$HOME/.ssh/id_ed25519.pub" \
    ./deploy/provision.sh
```

This creates the DNS zone, the SSH keys, the egress pool, the server, the
records, the bucket, and the GitHub handoff. It stops at the first step that
needs you, which is normally the delegation.

## 2. Delegate the domain

The `delegation` step prints nameservers. Add them at your registrar for
`relays.to`, then rerun:

```bash
./deploy/provision.sh
```

The step waits ten minutes, so you can set the delegation while it waits. If it
times out, rerun once the registrar has caught up.

## 3. Add the OAuth credentials

```bash
dotenvx set GITHUB_CLIENT_ID "<id>" -f .env.production
dotenvx set GITHUB_CLIENT_SECRET "<secret>" -f .env.production
git add .env.production && git commit -m "Add OAuth credentials" && git push
```

## 4. Deploy

```bash
gh workflow run deploy.yml
```

The workflow runs from `main` and skips itself on any other ref, so dispatch it
from `main`. It also fires on its own after CI passes there, and fails harmlessly
until provisioning has set the `KUBECONFIG` secret.

It applies `deploy/k8s`, runs the migration, refreshes the virus signatures,
and rolls out every workload.

The deploy token holds a Role in the `relay` namespace alone, so the first boot
creates the cluster-scoped Dozzle RBAC. See `deploy/cloud-init.yaml.tmpl`.

## 5. Check it

```bash
curl https://relays.to/health/node/        # host resources, the container probes
curl https://relays.to/health/application/ # every dependency relay controls
curl https://relays.to/health/pipeline/    # third-party status pages the pipeline depends on
openssl s_client -connect smtp.relays.to:587 -starttls smtp
openssl s_client -connect mx1.relays.to:25 -starttls smtp
dig +short pg.relays.to storage.relays.to
```

Then confirm the cluster itself is healthy:

```bash
hcloud server ssh relays.to "sudo k3s kubectl get pods -n relay"
hcloud server ssh relays.to "sudo k3s kubectl get events -n relay --sort-by=.lastTimestamp | tail"
```

Every pod should be `Running` with a `1/1` ready count.

## Rerunning and inspecting

```bash
./deploy/provision.sh              # run whatever is not done yet
./deploy/provision.sh records      # run one step
./deploy/provision.sh --status     # what is done, what is pending
./deploy/provision.sh --list       # the steps, in order
```

The steps are `zone`, `delegation`, `keys`, `egress`, `server`, `records`,
`propagation`, `storage` and `environment`. Each checks the real resource
before it changes anything, so a rerun skips what exists and never rotates a
credential that is live. What a run created lands in `deploy/.state/`, which is
git-ignored and safe to delete.

## When it stops

It prints what it needs and halts. Fix that, then rerun the same command.

- **No SSH yet**: the server is still booting. Rerun in a minute.
- **No cluster yet**: k3s is still installing, or cloud-init failed. Check
  `cloud-init status --long` and `/var/log/cloud-init-output.log` on the server,
  then rerun. On a fresh box this is normally a minute of patience.
- **Records pending**: a resolver cached the old answer. Rerun in a few minutes.
- **`.env.keys` missing**: restore the key that decrypts `.env.production`.
- **Pod stops at start**: the entrypoint is `dotenvx run --strict`, which halts
  instead of falling back to Django's defaults. Read the pod log. A missing
  `.env.production` or a missing `DOTENV_PRIVATE_KEY_PRODUCTION` both stop it.
- **Pool short**: run `./deploy/provision.sh egress`.

## Changing the deployment

Everything else is fixed for one server in `fsn1`, running k3s on
`ubuntu-24.04`, with its bucket alongside. Three values are worth setting:

- `SMTP_FLOATING_IP_COUNT` (default `2`): the egress pool size. Raise it to keep
  a spare for rotation, then run `./deploy/provision.sh egress records`.
- `SERVER_TYPE` (default `ccx33`) and `SERVER_LOCATION` (default `fsn1`): the
  box. The server step checks the pairing against the API before creating
  anything.
- `S3_BUCKET` (default `relay-<hostname>`): bucket names are unique across
  Hetzner Object Storage, so override it when the derived name is taken.

The k3s install flags live in `deploy/config.sh` as `K3S_INSTALL_FLAGS`. They
disable Traefik and ServiceLB, because Caddy is the ingress and nothing uses a
LoadBalancer Service, and turn on encryption at rest for Secrets.

### Changing a setting

The image carries the encrypted `.env.production` and decrypts it at container
start, so a change to it only reaches the cluster inside a new image. Push the
commit and the deploy workflow rebuilds. `CONVENTIONS.md` covers which values the
workflow derives and why.

### Reinstalling the server

A box that predates this guide, or one that is beyond repair, needs
reinstalling rather than patching. Rebuilding reinstalls the same server, so
every address it holds survives: the primary IP, the floating IPs, and the
records and PTRs that point at them. **No DNS change is needed.** The disk is
erased, and the platform is down until the deploy workflow runs again.

It needs `deploy/id_ed25519.pub`, because first boot installs that key for the
`github` user. The pair is git-ignored and lives only in the checkout that
created it, so a fresh clone has none. If it is missing, run
`./deploy/provision.sh keys` first: that creates a pair when neither file
exists, or derives the public key from the private one. It stops with
instructions if the key uploaded to Hetzner holds different material, which is
a `hcloud ssh-key delete` away.

```bash
./deploy/provision.sh keys
./deploy/steps/05-server.sh --reinit
./deploy/provision.sh              # carry on with the remaining steps
```

Run the step directly rather than through `provision.sh`. Rebuilding is
destructive, and a step that a bare `./deploy/provision.sh` can reach is one
that a rerun can trigger by accident.

Reinstalling is also the decommissioning. The deployment that ran on the box
goes with the disk, and nothing is left behind, because the server, the floating
IPs, the zone and the bucket are all reused rather than replaced. Take a
snapshot first if you want a way back.

### Changing the server image

`SERVER_IMAGE` is a first-boot setting, so an image change is a reinstall rather
than an edit: set it in `deploy/config.sh`, then reinstall as above. That keeps
the addresses and erases the disk. Once the platform carries real data, treat it
as a planned move.

## Rotating a blacklisted address

Drop it from both settings and push:

```bash
dotenvx set RELAY_DNS_SMTP_IPS "<remaining>,<server_ip>" -f .env.production -p
dotenvx set RELAY_SMTP_SOURCE_IPS "<remaining>,<server_ip>" -f .env.production -p
git add .env.production && git commit -m "Switch SMTP IP" && git push
```

Keep the address assigned until it clears, then add it back the same way.
Set `SMTP_FLOATING_IP_COUNT` high enough that a spare is always available.

## Day-2

```bash
hcloud server ssh relays.to                    # log in
hcloud server metrics relays.to                # CPU, disk, network
hcloud server enable-backup relays.to
hcloud server create-image --type snapshot --description "relay Docker, pre-k3s $(date +%F)" relays.to
hcloud all list --paid                         # what costs money
```

`/etc/rancher/k3s/k3s.yaml` on the server is the admin kubeconfig, readable by
root only. Copy it locally to use `kubectl` without going through SSH every
time, and keep it root-only on your machine too, since it is the cluster
credential:

```bash
umask 077 && hcloud server ssh relays.to "sudo cat /etc/rancher/k3s/k3s.yaml" > ~/.kube/relay.yaml
kubectl --kubeconfig ~/.kube/relay.yaml get pods -n relay
```

To grow the egress pool, raise `SMTP_FLOATING_IP_COUNT` and run the `egress`
and `server` steps. Those create and assign the address but do not configure the
box, because `user_data` only applies at first boot. Add it through netplan,
which keeps the whole pool through a reconfiguration:

```bash
hcloud server ssh relays.to "sudo netplan set --origin-hint 61-floating-ip-pool 'ethernets.eth0.addresses=[<new_ip>/32]' && sudo netplan apply"
```

Not `ip addr add`: an address bound by hand belongs to no configuration, and
networkd drops it the next time it reconfigures eth0.

### Certificates

The mail servers read Caddy's certificates at startup and never re-read them, so
**a rotation needs an `msa` and `mta` restart**:

```bash
kubectl --kubeconfig ~/.kube/relay.yaml rollout restart deployment/msa deployment/mta -n relay
```

Every deploy rolls those services, so this normally takes care of itself.

### Logs

Dozzle reads pod logs through the Kubernetes API. It is not published to the
internet. Tunnel to the dashboard:

```bash
kubectl --kubeconfig ~/.kube/relay.yaml port-forward -n relay svc/dozzle 5000:8080
```

The dashboard and the Dozzle MCP server in `.mcp.json` answer on
`http://127.0.0.1:5000`.

### Backups

The nightly workflow writes an encrypted `backup.dump.gpg` artifact. To restore,
decrypt with the private key matching `.box/backup.pub`, then load the
custom-format dump:

```bash
gpg --decrypt backup.dump.gpg > backup.dump
kubectl --kubeconfig ~/.kube/relay.yaml cp backup.dump relay/postgres-0:/tmp/backup.dump
kubectl --kubeconfig ~/.kube/relay.yaml exec -n relay postgres-0 -- \
    pg_restore -U postgres -d postgres --clean --if-exists /tmp/backup.dump
```

An untested restore is not a backup. Run that against a scratch database at
least once before you need it.

### Upgrading k3s

```bash
hcloud server ssh relays.to "curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC='server --disable traefik --disable servicelb --secrets-encryption' sh -"
```

Re-running the installer is the upgrade path, and repeating the same flags
keeps the cluster's shape. Read the release notes first: a minor version can
move Kubernetes APIs, and the manifests here are not version pinned.

### Known limitations

- **One node.** Two replicas survive a replica going unhealthy, not the node
  failing. A second and third node is the next step, and it is also when
  `postgres` and `redis-tasks` can gain real replication rather than just probes.
- **Caddy and dnsdist run one replica each**, because both bind the node's ports
  and two pods cannot share a port on one node. That is also what preserves the
  real client address on the mail path.
- **The namespace is flat**, because no NetworkPolicies are defined yet.
- **The API server answers on the public internet** at `:6443`, because the
  GitHub runner reaches it at the server's address and no Hetzner Cloud Firewall
  is created. Either restrict 6443 to the runner with a firewall, or deploy over
  an SSH tunnel. The token it hands out does not expire, so rotating it means
  deleting the `deploy-token` secret and running the `environment` step again.
- **The deploy token can create pods**, which on a single node is node root: a
  privileged pod with a `hostPath` mount reaches the k3s admin kubeconfig. No
  Pod Security Admission level is enforced, because baseline forbids
  `hostNetwork` and `caddy`, `dnsdist` and `sender` need it, so enforcing it
  means exempting those three first.

## Architecture

The services, the ports and the message path are in the
[root README](../README.md#architecture).
