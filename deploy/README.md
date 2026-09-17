# Deploy relay to Hetzner

One script, one server. It stops wherever it needs you, and rerunning the same
command carries on from there.

## Before you start

Install nothing. `hcloud`, `aws`, `jq`, `gh`, `dotenvx`, `envsubst`,
`ssh-keygen` and `dig` are already on this machine.

Three things to have ready:

1. **A Hetzner token**, in hcloud:

   ```bash
   HCLOUD_TOKEN="<token>" hcloud context create relay --token-from-env
   ```

1. **`.env.keys`** in the repo root. It decrypts the committed
   `.env.production` and is git-ignored, so restore it from wherever you keep
   it.

1. **Object Storage credentials**, exported for the `storage` step:

   ```bash
   export AWS_ACCESS_KEY_ID="<key>"
   export AWS_SECRET_ACCESS_KEY="<secret>"
   ```

Then open outbound ports 25 and 465 in the Console. Everything works without
them except mail delivery.

## 1. Provision

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

## 5. Check it

```bash
curl https://relays.to/health/
curl https://relays.to/health/soa/
openssl s_client -connect smtp.relays.to:587 -starttls smtp
dig +short pg.relays.to storage.relays.to
```

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
- **Records pending**: a resolver cached the old answer. Rerun in a few minutes.
- **`.env.keys` missing**: restore the key that decrypts `.env.production`.
- **Pool short**: run `./deploy/provision.sh egress`.

## Changing the deployment

Everything else is fixed for one server in `fsn1`, on Hetzner's `docker-ce`
image, with its bucket alongside. Three values are worth setting:

- `SMTP_FLOATING_IP_COUNT` (default `2`): the egress pool size. Raise it to keep
  a spare for rotation, then run `./deploy/provision.sh egress records`.
- `SERVER_TYPE` (default `ccx33`) and `SERVER_LOCATION` (default `fsn1`): the
  box. The server step checks the pairing against the API before creating
  anything.
- `S3_BUCKET` (default `relay-<hostname>`): bucket names are unique across
  Hetzner Object Storage, so override it when the derived name is taken.

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
hcloud server create-image --type snapshot --name relay-$(date +%F) relays.to
hcloud all list --paid                         # what costs money
```

To grow the pool, raise `SMTP_FLOATING_IP_COUNT`, run the `egress` and `server`
steps, then bind the new address, because `user_data` only applies at first
boot:

```bash
hcloud server ssh relays.to "sudo ip addr add <new_ip>/32 dev eth0"
```

The same applies to the two settings `user_data` writes at first boot, which a
box created before them does not have. A deploy opens a session per service,
and sshd drops the tenth without the first; the DNS container cannot bind `:53`
while the resolved stub listener holds it:

```bash
# sshd drops the tenth session a deploy opens
hcloud server ssh relays.to "printf '%s\n' 'MaxStartups 100:30:200' | sudo tee /etc/ssh/sshd_config.d/10-maxstartups.conf && sudo systemctl reload ssh"

# the resolved stub listener holds :53, which the DNS container needs
hcloud server ssh relays.to "sudo systemctl disable --now systemd-resolved && sudo rm -f /etc/resolv.conf && printf 'nameserver 1.1.1.1\nnameserver 9.9.9.9\n' | sudo tee /etc/resolv.conf"

# containers created before that still name 127.0.0.53 as their upstream, which
# no longer answers, so restart them to pick up the new resolvers. Without this
# they resolve nothing, and Caddy cannot even reach the ACME directory.
hcloud server ssh relays.to 'docker restart $(docker ps -q)'
```

## Architecture

The services, the ports and the message path are in the
[root README](../README.md#architecture).
