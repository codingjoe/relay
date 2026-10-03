# Deploy relay to Hetzner

One script, one server. It stops wherever it needs you, and rerunning the same
command carries on from there.

The server runs a single-node Talos Linux cluster. Talos is an immutable
distribution with no SSH and no package manager: `talosctl` administers the
machine, `kubectl` the cluster. This guide covers provisioning and day-to-day
operations; the deployment's internals live in `deploy/k8s/`.

## Before you start

`hcloud`, `aws`, `jq`, `gh`, `dotenvx`, `envsubst`, `dig` and `kubectl` are
already on this machine. Two tools are not, and this guide needs both.

`talosctl`, on the release `TALOS_VERSION` names (`v1.14.2` today). A client one
minor release away still talks to the node, but keep every workstation on the
pinned release, the way the upgrade workflow downloads the release it installs:

```bash
brew tap siderolabs/tap
brew install siderolabs/tap/talosctl@1.14
brew link --force siderolabs/tap/talosctl@1.14   # keg-only, so link it
```

`hcloud-upload-image` `v1.5.0`, which writes the disk image into a Hetzner
snapshot. Take the release binary, or build it with a recent Go toolchain:

```bash
go install github.com/apricote/hcloud-upload-image@v1.5.0
```

Three things to have ready:

1. **A Hetzner token**, in hcloud, and exported for the image step:

   ```bash
   HCLOUD_TOKEN="<token>" hcloud context create relay --token-from-env
   export HCLOUD_TOKEN="<token>"
   ```

   `hcloud` remembers the context; `hcloud-upload-image` does not, and reads the
   token from the environment.

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

```bash
RELAY_HOSTNAME="relays.to" ./deploy/provision.sh
```

A server that this guide did not create keeps what it has: the server step
stops on a box whose image is not the snapshot it uploaded, and says so.
Reinstall it in place to move it to Talos, which keeps its addresses. See
[Rebuilding the server](#rebuilding-the-server).

The run walks these steps in order and stops at the first one that needs you,
which is normally the delegation:

| Step          | What it does                                                                                                                                               |
| ------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `image`       | uploads the Talos hcloud disk image as a snapshot, once per version                                                                                        |
| `zone`        | creates the Hetzner Cloud DNS zone                                                                                                                         |
| `delegation`  | waits for the registrar to delegate the domain to that zone                                                                                                |
| `keys`        | generates the cluster secrets, the machine config and the client configs                                                                                   |
| `egress`      | creates the pool of floating IPs that outbound mail is sent from                                                                                           |
| `server`      | creates the server from the snapshot, hands it the machine config, pushes the current render to a node it keeps, bootstraps etcd and writes the kubeconfig |
| `records`     | publishes the zone's records and the PTR record of every egress address                                                                                    |
| `propagation` | waits until public resolvers answer with those records                                                                                                     |
| `storage`     | creates the Object Storage bucket for stored mail                                                                                                          |
| `environment` | writes the GitHub variables and secrets, and the production environment file                                                                               |
| `cluster`     | installs the add-ons Kubernetes does not bundle: local storage, metrics and kubelet serving certificates                                                   |

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

It installs the environment and runs `manage.py check --deploy` against
`.env.production` before it opens the cluster connection, with warnings as
failures. It then applies `deploy/k8s`, runs the migration, refreshes the virus
signatures, and rolls out every workload. A later failure rolls the workloads
the release moved back to the image they ran before; migrations are not
reversed.

The deploy token holds a Role in the `relay` namespace alone, so the first boot
applies the cluster-scoped Dozzle RBAC and labels the namespace for its
privileged pods. See `deploy/talos/machine-config.patch.yaml.tmpl`.

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
export KUBECONFIG=deploy/.state/talos/kubeconfig
kubectl get pods -n relay
kubectl get events -n relay --sort-by=.lastTimestamp | tail
```

Every long-running pod should be `Running` with a `1/1` ready count: each one
carries a liveness probe that restarts a hung process and a readiness probe that
proves it is answering. The two Jobs report `Completed` instead. A pod that
never becomes ready describes why under `kubectl describe pod`.

## Rerunning and inspecting

```bash
./deploy/provision.sh              # run whatever is not done yet
./deploy/provision.sh records      # run one step
./deploy/provision.sh --status     # what is done, what is pending
./deploy/provision.sh --list       # the steps, in order
```

The steps are `image`, `zone`, `delegation`, `keys`, `egress`, `server`,
`records`, `propagation`, `storage`, `environment` and `cluster`. Each checks the
real resource before it changes anything, so a rerun skips what exists and never
rotates a credential that is live. What a run created lands in `deploy/.state/`,
which is git-ignored and safe to delete, except `deploy/.state/talos/`, which
holds the cluster secrets and the configs they signed, and is the only copy.

## When it stops

It prints what it needs and halts. Fix that, then rerun the same command.

- **No Talos API yet**: the node is still installing itself to disk. Rerun in a
  minute, or read what the boot did:
  `talosctl --talosconfig deploy/.state/talos/talosconfig dmesg`.
- **No cluster yet**: the first boot did not finish, so the namespace and the
  deploy token are not there. The same `dmesg` says why; a node that never
  answers needs a reinstall, not patience.
- **Records pending**: a resolver cached the old answer. Rerun in a few minutes.
- **`.env.keys` missing**: restore the key that decrypts `.env.production`.
- **Pod stops at start**: the entrypoint is `dotenvx run --strict`, which halts
  instead of falling back to Django's defaults. Read the pod log. A missing
  `.env.production` or a missing `DOTENV_PRIVATE_KEY_PRODUCTION` both stop it.
- **Pool short**: run `./deploy/provision.sh egress`.

## Changing the deployment

Everything else is fixed for one server in `fsn1`, booting the pinned Talos
release, with its bucket alongside. The values worth setting:

- `TALOS_VERSION` (default `v1.14.2`) and `TALOS_SCHEMATIC` (Hetzner's public
  one): the Talos release, and the Image Factory build of it, that every server
  boots and installs. A version change needs the `image` step again; see
  [Upgrades](#upgrades).
- `SMTP_FLOATING_IP_COUNT` (default `2`): the egress pool size. Raise it to keep
  a spare for rotation; see [Growing the egress pool](#growing-the-egress-pool).
- `SERVER_TYPE` (default `ccx33`) and `SERVER_LOCATION` (default `fsn1`): the
  box. The server step checks the pairing against the API before creating
  anything.
- `S3_BUCKET` (default `relay-<hostname>`): bucket names are unique across
  Hetzner Object Storage, so override it when the derived name is taken.

The machine config lives in `deploy/talos/machine-config.patch.yaml.tmpl`. It
carries the egress pool, the resolvers, the kubelet serving certificate setting
and the namespace's admission labels. The server step renders it onto the
config the keys step generated and either hands the result to a new or rebuilt
node as user_data or pushes it to the running node with `talosctl apply-config`.
Nothing else configures the machine: Talos has no cloud-init, no netplan and no
SSH.

### Changing a setting

The image carries the encrypted `.env.production` and decrypts it at container
start, so a change to it only reaches the cluster inside a new image. Push the
commit and the deploy workflow rebuilds. `CONVENTIONS.md` covers which values the
workflow derives and why.

### Rebuilding the server

A box that predates this guide, or one that is beyond repair, is reinstalled
rather than patched. `hcloud server rebuild` reinstalls the same server, so
every address it holds survives: the primary IP, the floating IPs, and the
records and PTRs that point at them. **No DNS change is needed.** The disk is
erased, the etcd bootstrap runs again, and the platform is down until the deploy
workflow runs again.

Rebuilding is also the decommissioning: the deployment that ran on the box goes
with the disk, and nothing is left behind, because the server, the floating IPs,
the zone and the bucket are all reused rather than replaced.

```bash
./deploy/steps/05-server.sh --reinit
./deploy/provision.sh              # carry on with the remaining steps
```

Run the step directly rather than through `provision.sh`. Rebuilding is
destructive, and a step that a bare `./deploy/provision.sh` can reach is one
that a rerun can trigger by accident.

The snapshot is uploaded once per Talos version: `hcloud-upload-image` boots a
temporary server to write the disk, so the `image` step runs only when the
snapshot for the pinned version is missing. Move `TALOS_VERSION` in
`deploy/config.sh`, run `./deploy/provision.sh image`, then rebuild onto the new
release.

## Growing the egress pool

Raise `SMTP_FLOATING_IP_COUNT` and rerun the provisioner. The address is bound
on the running node and advertised, without a reinstall:

```bash
SMTP_FLOATING_IP_COUNT=3 ./deploy/provision.sh
```

The `egress` step creates each missing floating IP. The `server` step assigns
it, renders the machine config with the whole pool and pushes that render to
the running node with `talosctl apply-config`, which binds the address in place.
The same run publishes its PTR record, and the `environment` step compares the
live pool with `RELAY_DNS_SMTP_IPS` and `RELAY_SMTP_SOURCE_IPS` in
`.env.production`: when the two differ it rewrites both, so the new address is
advertised. Commit `.env.production` and dispatch the deploy workflow, which
starts sending from the new address.

The count comes from the environment, so keep exporting it for later runs; it
is not recorded in `deploy/.state/`.

Never bind an address by hand: no `ip addr add`, no netplan. Talos has neither,
and an address the machine config does not know is gone at the next boot.

## Rotating a blacklisted address

Dropping the address from the two settings changes what relay advertises, not
what the machine config binds, and it does not survive the next full
`./deploy/provision.sh` run: the `environment` step sees a live pool that no
longer matches `.env.production` and rewrites both values from the pool. The
address comes back as soon as that rewrite is committed and deployed, so use the
drop for a pause while a listing clears:

```bash
dotenvx set RELAY_DNS_SMTP_IPS "<remaining>,<server_ip>" -f .env.production --plain
dotenvx set RELAY_SMTP_SOURCE_IPS "<remaining>,<server_ip>" -f .env.production --plain
git add .env.production && git commit -m "Switch SMTP IP" && git push
```

To rotate the address out for good, delete its floating IP and rerun the
provisioner, leaving `SMTP_FLOATING_IP_COUNT` alone so the pool keeps its size:

```bash
hcloud floating-ip list --selector relay=smtp   # names to addresses
hcloud floating-ip delete relays.to-smtp-2
./deploy/provision.sh
```

The `egress` step recreates the deleted name with a fresh address. That address
is not assigned yet, so the `server` step runs: it renders the pool without the
blacklisted address and pushes that render to the running node, which replaces
it in the link config. The `records` step overwrites the sender record and the
PTR of that pool position, and the `environment` step republishes the pool,
which now matches `.env.production` again. Nothing is reinstalled.

Keep `SMTP_FLOATING_IP_COUNT` high enough that a spare is always available.

## Access

Both management endpoints answer the public internet, because no Hetzner Cloud
Firewall is created: the Talos API on `:50000` and the Kubernetes API server on
`:6443`. Neither is open. Talos and `kubectl` authenticate with client
certificates signed by the cluster's own CA, which is mutual TLS, and the deploy
workflow carries the namespace-scoped deploy token, which does not expire. A
Hetzner Cloud Firewall that admits only your addresses is the alternative when
the ports have to be closed; it is a firewall change, not a node change.

The keys step issues two client configs, each with a role of its own:

- `deploy/.state/talos/talosconfig`, `os:admin`: the whole machine API.
- `deploy/.state/talos/talosconfig-reader`, `os:reader`: the read-only methods,
  logs, dmesg, netstat, processes, services. It cannot read file contents and
  cannot hand out a kubeconfig. Give this one to anyone who only needs to look.

**Client certificates last one year, and Talos does not rotate them.** Only the
server side rotates; a client config simply stops working one day, which is the
day you want `deploy/.state/talos/secrets.yaml` at hand. That bundle signs every
client certificate, holds the etcd encryption key and is the cluster's recovery
input, so keep it out of the repository and back it up where only you can read
it. Reissue a client config from it:

```bash
talosctl gen config relays.to https://relays.to:6443 \
    --with-secrets deploy/.state/talos/secrets.yaml \
    --output-types talosconfig -o deploy/.state/talos/talosconfig --force
talosctl --talosconfig deploy/.state/talos/talosconfig config endpoint relays.to
talosctl --talosconfig deploy/.state/talos/talosconfig config node relays.to
```

## Day-2

```bash
export TALOSCONFIG=deploy/.state/talos/talosconfig
export KUBECONFIG=deploy/.state/talos/kubeconfig

hcloud server metrics relays.to        # CPU, disk, network
hcloud all list --paid                 # what costs money

kubectl get nodes
talosctl version
talosctl logs kubelet                  # one service's log
talosctl dmesg                         # the kernel ring
talosctl netstat                       # host connections and sockets
kubectl debug node/<name> -n relay -it --image=alpine   # a shell on the host
```

The admin kubeconfig is the one the server step wrote to
`deploy/.state/talos/kubeconfig`. Install it as your own, or re-issue it from
the node when it has expired:

```bash
talosctl kubeconfig --force --merge=false ~/.kube/relay.yaml
kubectl --kubeconfig ~/.kube/relay.yaml config set-context --current --namespace relay
export KUBECONFIG=~/.kube/relay.yaml
```

Both kubeconfigs default to the `relay` namespace: this admin one, and the
deploy token the workflows carry. Plain `kubectl get pods` reaches the relay
objects, and the workflows' explicit `--namespace relay` stays valid and is no
longer needed.

The namespace stays even though the cluster hosts nothing else: the deploy
token's Role is scoped to it, the privileged Pod Security Admission label lives
on it so a stray apply elsewhere is not privileged, and Dozzle's delete and exec
Role stays inside it.

Keep `-n relay` on `kubectl debug`: a node debugger mounts the host filesystem
in a pod, and `relay` is the namespace that admits it.

### Certificates

The mail servers read Caddy's certificates at startup and never re-read them, so
**a rotation needs an `msa` and `mta` restart**:

```bash
kubectl rollout restart deployment/msa deployment/mta -n relay
```

Every deploy rolls those services, so this normally takes care of itself.

### Edge compression and caching

Static files are served by the app through ServeStatic, with pre-compressed
`zstd` and `gzip` variants. Caddy's `{$HOSTNAME}` block in
`deploy/k8s/caddy/Caddyfile` additionally compresses on the fly with `br` and
keeps publicly cacheable responses in `caddy-redis`, so its cache survives a
Caddy restart.

Caddy creates its cache storer once at startup. If it starts before
`caddy-redis` answers, it logs a Redis init error and keeps cache entries in
memory until its next restart, so restart the deployment after such a race:

```bash
kubectl --kubeconfig ~/.kube/relay.yaml rollout restart deployment/caddy -n relay
```

### Logs

One Dozzle instance watches every namespace through the Kubernetes API. It is
not published to the internet. Tunnel to the dashboard:

```bash
kubectl port-forward -n relay svc/dozzle 5000:8080
```

The dashboard and the Dozzle MCP server in `.mcp.json` answer on
`http://127.0.0.1:5000`.

Talos keeps no system journal on disk. Service and kernel logs live in a ring
buffer that a reboot clears, and container logs live on the ephemeral disk,
which a reinstall erases. There is no `/var/log` that outlives the node, so
Dozzle and `talosctl logs` show the node that is running now. The transmission
records in the database, and Sentry, are the log that stays.

### Backups

The nightly workflow writes an encrypted `backup.dump.gpg` artifact. To restore,
decrypt with the private key matching `.box/backup.pub`, then load the
custom-format dump:

```bash
gpg --decrypt backup.dump.gpg > backup.dump
kubectl cp backup.dump relay/postgres-0:/tmp/backup.dump
kubectl exec -n relay postgres-0 -- \
    pg_restore -U postgres -d postgres --clean --if-exists /tmp/backup.dump
```

An untested restore is not a backup. Run that against a scratch database at
least once before you need it.

An etcd snapshot is not a backup of the platform. It holds the control-plane
objects (Secrets, Deployments, RBAC, the deploy token) and none of the data
in the PersistentVolumes, so it cannot replace the dump above. On a single node
it is still the only way back to those objects after the disk is lost, so keep
one when you change something cluster-level:

```bash
talosctl etcd snapshot relay.db.snapshot
```

Restoring it is the documented disaster-recovery procedure, not a warm restore:
a freshly installed node that then runs
`talosctl bootstrap --recover-from relay.db.snapshot`, while the PVC data has to
come back from the dump.

## Upgrades

Talos has no package manager, so there is no `unattended-upgrades` and no
partial update: the release is the patch. The node moves to a new release in one
image, and Kubernetes moves with it: `deploy/upgrade.sh` passes
`KUBERNETES_VERSION`, the Kubernetes release that ships in `TALOS_VERSION`, to
`talosctl upgrade-k8s --to`, so a `talosctl` binary from another release cannot
move the cluster to its own default.

The `📦 Upgrade Node` workflow runs `deploy/upgrade.sh` every Wednesday at
01:00 UTC, inside the 01:00-03:00 window when mail traffic is lowest. Run the
same script by hand on an afternoon you are watching:

```bash
deploy/upgrade.sh
```

Before it acts, the gate reads Hetzner's status page and skips the run when the
page reports an unresolved incident, or a maintenance that overlaps the window.
A page that cannot be read fails the run loudly instead of upgrading blind.
The upgrade drains and reboots the node, so mail is queued and retried; an
interrupted run can leave the node cordoned, which `kubectl get nodes` shows and
`kubectl uncordon <name>` clears. The upgrade workflow and the deploy workflow
share one concurrency group, so they take turns.

To move a release, set `TALOS_VERSION` and `KUBERNETES_VERSION` in
`deploy/config.sh`: the Talos release, and the Kubernetes release that ships in
it. Then run the two steps that carry it:

```bash
./deploy/provision.sh image environment
```

The `image` step uploads the snapshot the next rebuild boots, and the
`environment` step publishes the installer the upgrade installs. Then dispatch
`gh workflow run upgrade.yml`, or wait for Wednesday. Read the release notes
first: a minor version can move Kubernetes APIs, and the manifests here are not
version pinned.

## Adding a node

The cluster is one node. A second and third node join from the same secrets, so
the certificates, the etcd encryption key and the cluster identity match. This
is a sketch rather than a step: `./deploy/provision.sh server` creates exactly
one server, and the egress pool belongs to it.

The patched machine config exists only while the server step runs: it renders
`deploy/talos/machine-config.patch.yaml.tmpl` onto the generated
`deploy/.state/talos/controlplane.yaml` in a temporary file, hands that to the
node and deletes it. The base carries the secrets and the cluster certificates,
but none of the patch's link, resolver or bootstrap documents, and the patch
deletes the generator's install document, so the config handed to the node
carries no installer image. Build the new node's config the same way, from the
same two inputs:

```bash
source deploy/config.sh   # RELAY_HOSTNAME, TALOS_VERSION, TALOS_INSTALLER, TALOS_DIR

# the same secrets the cluster was generated from, and the same installer
talosctl gen config "$RELAY_HOSTNAME" "https://$RELAY_HOSTNAME:6443" \
    --with-secrets "$TALOS_DIR/secrets.yaml" --talos-version "$TALOS_VERSION" \
    --install-image "$TALOS_INSTALLER" \
    --output-types controlplane -o /tmp/node.yaml \
    --with-docs=false --with-examples=false

# the same patch, rendered with the namespace and the addresses this node carries
RELAY_NAMESPACE=relay LINK_ADDRESSES='{address: <pool address>/32}' \
    envsubst '${LINK_ADDRESSES} ${RELAY_NAMESPACE}' \
    < deploy/talos/machine-config.patch.yaml.tmpl > /tmp/node.patch
talosctl machineconfig patch /tmp/node.yaml --patch @/tmp/node.patch -o /tmp/node.yaml
talosctl validate --config /tmp/node.yaml --mode cloud
```

Create the node with that config as `user_data`, the way the server step does;
`hcloud image list --type snapshot --selector relay=image` names the snapshot:

```bash
hcloud server create --name <name> --type "$SERVER_TYPE" --image <snapshot id> \
    --location "$SERVER_LOCATION" --user-data-from-file /tmp/node.yaml
```

For a node that does not run the control plane, generate the worker variant with
`--output-types worker`. The patch's link document names the egress pool, and a
Hetzner floating IP is assigned to one server at a time, so only the node that
carries the pool takes those addresses. Drop that document for a node that must
not claim them. The resolver and kubelet documents apply to any node.

Etcd quorum wants an odd number of members: three control planes tolerate one
failing, two tolerate none. The cluster endpoint is a single address, so a
multi-node cluster also needs a stable way in: a virtual IP or a Hetzner Cloud
Load Balancer in front of `:6443`, with the endpoint and every machine config
pointing at it. Without one, a control plane going down takes the API with it.

## Known limitations

- **One node.** Two replicas survive a replica going unhealthy, not the node
  failing. Three control planes with a virtual IP or a Hetzner Cloud Load
  Balancer are the next step, and it is also when `postgres` and `redis-tasks`
  can gain real replication rather than just probes. See
  [Adding a node](#adding-a-node).
- **Caddy and dnsdist run one replica each**, because both bind the node's ports
  and two pods cannot share a port on one node. That is also what preserves the
  real client address on the mail path.
- **The namespace is flat**, because no NetworkPolicies are defined, and the
  cluster's Flannel CNI enforces none anyway, so pod-to-pod traffic is
  unfiltered. See the node's machine config below.
- **Both management ports answer the public internet.** The Talos API on
  `:50000` and the Kubernetes API on `:6443` are protected by mutual TLS and by
  the namespace-scoped deploy token, not by a firewall. See [Access](#access).
- **The deploy token can create pods**, which on a single node is node root: a
  privileged pod the token creates can reach the host. That is why the namespace
  runs the privileged Pod Security Admission profile: `caddy`, `dnsdist` and
  `sender` need `hostNetwork`, which baseline forbids. The token itself stays
  inside the namespace and cannot touch cluster-scoped objects.
- **The node's machine config carries the cluster's private keys, and Hetzner
  serves it to anything on the node.** The first boot takes the config as
  Hetzner `user_data`, and Hetzner serves that blob from the instance metadata
  service at `169.254.169.254`, unauthenticated, to every process on the box.
  The document holds the machine and cluster bootstrap tokens, the machine,
  etcd, API-server and aggregator CA keys, the etcd secretbox key and the
  service-account key: the cluster's permanent PKI. Caddy terminates untrusted
  TLS, dnsdist answers DNS, and rspamd and the app parse mail, so code execution
  in any relay pod reads those keys and can mint cluster-admin credentials that
  never expire. Nothing inside the cluster gates the endpoint: Flannel enforces
  no NetworkPolicy, and the host-network pods bypass pod network controls
  anyway. The fix is outside the code: install from a hand-rolled ISO that never
  puts the config on the metadata service. The migration rejected that route to
  keep provisioning declared and repeatable. This is an accepted risk,
  not a defended boundary: treat the node as inside the trust boundary that
  holds the cluster keys.
- **The upgrade gate scrapes a web page.** Hetzner publishes no status API, so
  the gate reads `status.hetzner.com`; a change to that page fails the run
  loudly rather than upgrading blind. See [Upgrades](#upgrades).

## Architecture

The services, the ports and the message path are in the
[root README](../README.md#architecture).
