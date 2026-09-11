#!/usr/bin/env bash
#
# Provision relay on a single Hetzner Cloud server with the hcloud CLI.
#
# The script is idempotent: every resource is looked up before it is created,
# so re-running it is safe and never rotates live credentials.
#
# Required environment:
#   AWS_ACCESS_KEY_ID       Hetzner Object Storage access key
#   AWS_SECRET_ACCESS_KEY   Hetzner Object Storage secret key
#
# Optional environment (defaults in parentheses):
#   RELAY_HOSTNAME          (relay.example.com)  public hostname of the server
#   SERVER_TYPE             (cx22)               hcloud server type
#   SERVER_IMAGE            (ubuntu-24.04)       hcloud image
#   SERVER_LOCATION         (fsn1)               hcloud location
#   SMTP_FLOATING_IP_COUNT  (2)                  size of the SMTP egress pool
#   S3_ENDPOINT             (fsn1.your-objectstorage.com)
#   S3_REGION               (fsn1)
#   S3_BUCKET               (relay-<hostname with dots replaced by dashes>)
#   SSH_PUBLIC_KEY_FILES    (~/.ssh/id_ed25519.pub)  space separated
#   DEPLOY_KEY              (deploy/id_ed25519)  deploy key pair location
#
# See deploy/README.md for the full operator guide.

set -euo pipefail

log() {
    printf '\n==> %s\n' "$*"
}

warn() {
    printf 'warning: %s\n' "$*" >&2
}

fail() {
    printf 'error: %s\n' "$*" >&2
    exit 1
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$REPO_ROOT"

log "Checking prerequisites"
for command in hcloud aws jq envsubst ssh-keygen gh dotenvx python3; do
    command -v "$command" >/dev/null 2>&1 || fail "$command is required but not installed"
done

if ! hcloud server list >/dev/null 2>&1; then
    fail "hcloud is not authenticated. Run: HCLOUD_TOKEN=<token> hcloud context create relay --token-from-env"
fi

[ -n "${AWS_ACCESS_KEY_ID:-}" ] || fail "AWS_ACCESS_KEY_ID is not set"
[ -n "${AWS_SECRET_ACCESS_KEY:-}" ] || fail "AWS_SECRET_ACCESS_KEY is not set"

RELAY_HOSTNAME="${RELAY_HOSTNAME:-relay.example.com}"
SERVER_TYPE="${SERVER_TYPE:-cx22}"
SERVER_IMAGE="${SERVER_IMAGE:-ubuntu-24.04}"
SERVER_LOCATION="${SERVER_LOCATION:-fsn1}"
SMTP_FLOATING_IP_COUNT="${SMTP_FLOATING_IP_COUNT:-2}"
S3_ENDPOINT="${S3_ENDPOINT:-fsn1.your-objectstorage.com}"
S3_REGION="${S3_REGION:-fsn1}"
S3_BUCKET="${S3_BUCKET:-relay-${RELAY_HOSTNAME//./-}}"
S3_ENDPOINT_URL="https://${S3_ENDPOINT}"

DEPLOY_KEY="${DEPLOY_KEY:-$SCRIPT_DIR/id_ed25519}"
DEPLOY_KEY_NAME="${RELAY_HOSTNAME}-deploy"

export AWS_DEFAULT_REGION="$S3_REGION"

log "Deployment SSH key"
if [ -f "$DEPLOY_KEY" ]; then
    log "Reusing $DEPLOY_KEY"
else
    ssh-keygen -t ed25519 -N "" -C "deploy@${RELAY_HOSTNAME}" -f "$DEPLOY_KEY"
fi
DEPLOY_PUBLIC_KEY="$(cat "${DEPLOY_KEY}.pub")"

log "SSH keys in Hetzner Cloud"
if hcloud ssh-key describe "$DEPLOY_KEY_NAME" >/dev/null 2>&1; then
    log "SSH key $DEPLOY_KEY_NAME already exists"
else
    hcloud ssh-key create --name "$DEPLOY_KEY_NAME" --public-key-from-file "${DEPLOY_KEY}.pub" --label relay=deploy
fi

SERVER_SSH_KEYS=("$DEPLOY_KEY_NAME")
read -ra SSH_PUBLIC_KEY_FILES <<<"${SSH_PUBLIC_KEY_FILES:-$HOME/.ssh/id_ed25519.pub}"
for key_file in "${SSH_PUBLIC_KEY_FILES[@]}"; do
    if [ ! -f "$key_file" ]; then
        warn "SSH public key not found, skipping: $key_file"
        continue
    fi
    key_name="${RELAY_HOSTNAME}-$(basename "$key_file" .pub)"
    if hcloud ssh-key describe "$key_name" >/dev/null 2>&1; then
        log "SSH key $key_name already exists"
    else
        hcloud ssh-key create --name "$key_name" --public-key-from-file "$key_file" --label relay=deploy
    fi
    SERVER_SSH_KEYS+=("$key_name")
done

log "SMTP floating IPs (pool size $SMTP_FLOATING_IP_COUNT)"
SMTP_FLOATING_IP_NAMES=()
SMTP_POOL=()
for ((index = 1; index <= SMTP_FLOATING_IP_COUNT; index++)); do
    name="${RELAY_HOSTNAME}-smtp-${index}"
    if hcloud floating-ip describe "$name" >/dev/null 2>&1; then
        log "Floating IP $name already exists"
    else
        hcloud floating-ip create \
            --name "$name" \
            --type ipv4 \
            --home-location "$SERVER_LOCATION" \
            --label relay=smtp \
            --description "SMTP egress IP ${index} for ${RELAY_HOSTNAME}"
    fi
    SMTP_FLOATING_IP_NAMES+=("$name")
    SMTP_POOL+=("$(hcloud floating-ip describe "$name" -o json | jq -r '.ip')")
done
[ -n "${SMTP_POOL[0]:-}" ] || fail "could not read the address of ${SMTP_FLOATING_IP_NAMES[0]}"

# The cloud-init template consumes a space separated list for its shell loop,
# while the application reads both settings through env.list, which splits on
# commas and does not trim. Keep the two renderings apart.
SMTP_POOL_CSV="$(IFS=,; printf '%s' "${SMTP_POOL[*]}")"
SMTP_IPS="${SMTP_POOL[*]}"
export DEPLOY_PUBLIC_KEY SMTP_IPS

CLOUD_INIT="$(mktemp)"
trap 'rm -f "$CLOUD_INIT"' EXIT
envsubst "\${DEPLOY_PUBLIC_KEY} \${SMTP_IPS}" <"$SCRIPT_DIR/cloud-init.yaml.tmpl" >"$CLOUD_INIT"

log "Server $RELAY_HOSTNAME"
if hcloud server describe "$RELAY_HOSTNAME" >/dev/null 2>&1; then
    log "Server $RELAY_HOSTNAME already exists"
else
    server_args=(
        --name "$RELAY_HOSTNAME"
        --type "$SERVER_TYPE"
        --image "$SERVER_IMAGE"
        --location "$SERVER_LOCATION"
        --label relay=server
        --user-data-from-file "$CLOUD_INIT"
    )
    for key_name in "${SERVER_SSH_KEYS[@]}"; do
        server_args+=(--ssh-key "$key_name")
    done
    hcloud server create "${server_args[@]}"
fi

SERVER_ID="$(hcloud server describe "$RELAY_HOSTNAME" -o json | jq -r '.id')"
SERVER_IP="$(hcloud server ip "$RELAY_HOSTNAME")"

log "Assigning the SMTP floating IPs"
for name in "${SMTP_FLOATING_IP_NAMES[@]}"; do
    assigned_to="$(hcloud floating-ip describe "$name" -o json | jq -r '.server.id // empty')"
    if [ "$assigned_to" = "$SERVER_ID" ]; then
        log "Floating IP $name is already assigned"
    else
        hcloud floating-ip assign "$name" "$RELAY_HOSTNAME"
    fi
done

log "Reverse DNS records"
hcloud server set-rdns --ip "$SERVER_IP" --hostname "$RELAY_HOSTNAME" "$RELAY_HOSTNAME"
for index in "${!SMTP_FLOATING_IP_NAMES[@]}"; do
    hcloud floating-ip set-rdns \
        --ip "${SMTP_POOL[$index]}" \
        --hostname "smtp$((index + 1)).${RELAY_HOSTNAME}" \
        "${SMTP_FLOATING_IP_NAMES[$index]}"
done

log "Object Storage bucket $S3_BUCKET"
if aws --endpoint-url "$S3_ENDPOINT_URL" s3api head-bucket --bucket "$S3_BUCKET" >/dev/null 2>&1; then
    log "Bucket $S3_BUCKET already exists"
else
    aws --endpoint-url "$S3_ENDPOINT_URL" s3api create-bucket \
        --bucket "$S3_BUCKET" \
        --create-bucket-configuration "LocationConstraint=${S3_REGION}"
    aws --endpoint-url "$S3_ENDPOINT_URL" s3api put-bucket-ownership-controls \
        --bucket "$S3_BUCKET" \
        --ownership-controls 'Rules=[{ObjectOwnership=BucketOwnerPreferred}]'
fi

log "Waiting for SSH on $SERVER_IP"
SSH_KNOWN_HOSTS=""
for _ in $(seq 1 60); do
    SSH_KNOWN_HOSTS="$(ssh-keyscan -T 5 "$SERVER_IP" 2>/dev/null || true)"
    if [ -n "$SSH_KNOWN_HOSTS" ]; then
        break
    fi
    sleep 5
done
[ -n "$SSH_KNOWN_HOSTS" ] || fail "could not reach SSH on $SERVER_IP"

log "GitHub variables and secrets"
gh variable set SSH_HOSTNAME --body "$SERVER_IP"
gh variable set SSH_KNOWN_HOSTS --body "$SSH_KNOWN_HOSTS"
gh variable set HOSTNAME --body "$RELAY_HOSTNAME" --env production
gh secret set SSH_PRIVATE_KEY <"$DEPLOY_KEY"

RELAY_SMTP_IPS="${SMTP_POOL_CSV},${SERVER_IP}"

if [ -f "$REPO_ROOT/.env.keys" ]; then
    log "Updating .env.production"
    dotenvx set HOSTNAME "$RELAY_HOSTNAME" -f .env.production --plain
    dotenvx set RELAY_DNS_SMTP_IPS "$RELAY_SMTP_IPS" -f .env.production --plain
    dotenvx set RELAY_SMTP_SOURCE_IPS "$RELAY_SMTP_IPS" -f .env.production --plain
    dotenvx set AWS_S3_ENDPOINT_URL "$S3_ENDPOINT_URL" -f .env.production --plain
    dotenvx set AWS_STORAGE_BUCKET_NAME "$S3_BUCKET" -f .env.production --plain
    dotenvx set AWS_S3_REGION_NAME "$S3_REGION" -f .env.production --plain
    dotenvx set AWS_S3_ADDRESSING_STYLE path -f .env.production --plain
    dotenvx set AWS_S3_ACCESS_KEY_ID "$AWS_ACCESS_KEY_ID" -f .env.production
    dotenvx set AWS_S3_SECRET_ACCESS_KEY "$AWS_SECRET_ACCESS_KEY" -f .env.production

    for key in POSTGRES_PASSWORD REDIS_PASSWORD SECRET_KEY; do
        if dotenvx get "$key" -f .env.production >/dev/null 2>&1; then
            log "$key is already set, leaving it alone"
        else
            dotenvx set "$key" "$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')" -f .env.production
        fi
    done

    gh secret set DOTENV_PRIVATE_KEY_PRODUCTION --body "$(dotenvx get DOTENV_PRIVATE_KEY_PRODUCTION -f .env.keys)"

    cat <<EOF

Commit the encrypted environment file:

  git add .env.production
  git commit -m "Update production environment for $RELAY_HOSTNAME"
  git push
EOF
else
    warn ".env.keys is missing, so .env.production was not touched."
    cat <<EOF

Generate or restore .env.keys, then run these commands in the repository root:

  dotenvx set HOSTNAME "$RELAY_HOSTNAME" -f .env.production -p
  dotenvx set RELAY_DNS_SMTP_IPS "$RELAY_SMTP_IPS" -f .env.production -p
  dotenvx set RELAY_SMTP_SOURCE_IPS "$RELAY_SMTP_IPS" -f .env.production -p
  dotenvx set AWS_S3_ENDPOINT_URL "$S3_ENDPOINT_URL" -f .env.production -p
  dotenvx set AWS_STORAGE_BUCKET_NAME "$S3_BUCKET" -f .env.production -p
  dotenvx set AWS_S3_REGION_NAME "$S3_REGION" -f .env.production -p
  dotenvx set AWS_S3_ADDRESSING_STYLE path -f .env.production -p
  dotenvx set AWS_S3_ACCESS_KEY_ID "$AWS_ACCESS_KEY_ID" -f .env.production
  dotenvx set AWS_S3_SECRET_ACCESS_KEY "$AWS_SECRET_ACCESS_KEY" -f .env.production
  dotenvx set POSTGRES_PASSWORD "\$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')" -f .env.production
  dotenvx set REDIS_PASSWORD "\$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')" -f .env.production
  dotenvx set SECRET_KEY "\$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')" -f .env.production
  dotenvx get DOTENV_PRIVATE_KEY_PRODUCTION -f .env.keys | gh secret set DOTENV_PRIVATE_KEY_PRODUCTION

  git add .env.production
  git commit -m "Update production environment for $RELAY_HOSTNAME"
  git push
EOF
fi

cat <<EOF

Provisioning complete.

  Server             $RELAY_HOSTNAME ($SERVER_IP, $SERVER_TYPE in $SERVER_LOCATION)
  SMTP egress pool   ${SMTP_POOL[*]}
  Object Storage     $S3_ENDPOINT_URL ($S3_BUCKET)

Next steps:

  1. Point the DNS records for $RELAY_HOSTNAME at $SERVER_IP. See deploy/README.md.
  2. Trigger the deployment workflow:

       gh workflow run deploy.yml
EOF
