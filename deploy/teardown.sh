#!/usr/bin/env bash
#
# Remove every resource that provision.sh created.
#
# Reads the same configuration variables as provision.sh, so the same
# environment resolves the same resource names.
#
# Required environment:
#   AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY   only when DELETE_BUCKET=1
#
# Optional environment: see provision.sh, plus
#   FORCE=1           skip the confirmation prompt
#   DELETE_BUCKET=1   also delete the Object Storage bucket and its contents
#
# The server is deleted first, which releases the floating IPs. SSH keys are
# only removed when they are not used by another server.

set -euo pipefail

log() {
    printf '\n==> %s\n' "$*"
}

fail() {
    printf 'error: %s\n' "$*" >&2
    exit 1
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$(dirname "$SCRIPT_DIR")"

command -v hcloud >/dev/null 2>&1 || fail "hcloud is required but not installed"
command -v jq >/dev/null 2>&1 || fail "jq is required but not installed"
if ! hcloud server list >/dev/null 2>&1; then
    fail "hcloud is not authenticated. Run: HCLOUD_TOKEN=<token> hcloud context create relay --token-from-env"
fi
if [ "${DELETE_BUCKET:-0}" = "1" ]; then
    command -v aws >/dev/null 2>&1 || fail "aws is required when DELETE_BUCKET=1"
    [ -n "${AWS_ACCESS_KEY_ID:-}" ] || fail "AWS_ACCESS_KEY_ID is not set"
    [ -n "${AWS_SECRET_ACCESS_KEY:-}" ] || fail "AWS_SECRET_ACCESS_KEY is not set"
fi

RELAY_HOSTNAME="${RELAY_HOSTNAME:-relay.example.com}"
SERVER_LOCATION="${SERVER_LOCATION:-fsn1}"
SMTP_FLOATING_IP_COUNT="${SMTP_FLOATING_IP_COUNT:-2}"
S3_ENDPOINT="${S3_ENDPOINT:-fsn1.your-objectstorage.com}"
S3_REGION="${S3_REGION:-fsn1}"
S3_BUCKET="${S3_BUCKET:-relay-${RELAY_HOSTNAME//./-}}"
S3_ENDPOINT_URL="https://${S3_ENDPOINT}"

DEPLOY_KEY_NAME="${RELAY_HOSTNAME}-deploy"

export AWS_DEFAULT_REGION="$S3_REGION"

log "This will remove the following resources"
printf '  Server          %s\n' "$RELAY_HOSTNAME"
for ((index = 1; index <= SMTP_FLOATING_IP_COUNT; index++)); do
    printf '  Floating IP     %s-smtp-%s\n' "$RELAY_HOSTNAME" "$index"
done
printf '  SSH key         %s\n' "$DEPLOY_KEY_NAME"
if [ "${DELETE_BUCKET:-0}" = "1" ]; then
    printf '  Bucket          %s (with all stored mail)\n' "$S3_BUCKET"
fi

if [ "${FORCE:-0}" != "1" ]; then
    printf '\nType %s to continue: ' "$RELAY_HOSTNAME"
    read -r confirmation
    [ "$confirmation" = "$RELAY_HOSTNAME" ] || fail "aborted"
fi

if hcloud server describe "$RELAY_HOSTNAME" >/dev/null 2>&1; then
    log "Deleting server $RELAY_HOSTNAME"
    hcloud server delete "$RELAY_HOSTNAME"
else
    log "Server $RELAY_HOSTNAME does not exist"
fi

for ((index = 1; index <= SMTP_FLOATING_IP_COUNT; index++)); do
    name="${RELAY_HOSTNAME}-smtp-${index}"
    if ! hcloud floating-ip describe "$name" >/dev/null 2>&1; then
        log "Floating IP $name does not exist"
        continue
    fi
    if [ -n "$(hcloud floating-ip describe "$name" -o json | jq -r '.server.id // empty' 2>/dev/null)" ]; then
        hcloud floating-ip unassign "$name"
    fi
    log "Deleting floating IP $name"
    hcloud floating-ip delete "$name"
done

read -ra SSH_PUBLIC_KEY_FILES <<<"${SSH_PUBLIC_KEY_FILES:-$HOME/.ssh/id_ed25519.pub}"
SSH_KEY_NAMES=("$DEPLOY_KEY_NAME")
for key_file in "${SSH_PUBLIC_KEY_FILES[@]}"; do
    SSH_KEY_NAMES+=("${RELAY_HOSTNAME}-$(basename "$key_file" .pub)")
done

for key_name in "${SSH_KEY_NAMES[@]}"; do
    if ! hcloud ssh-key describe "$key_name" >/dev/null 2>&1; then
        log "SSH key $key_name does not exist"
        continue
    fi
    if [ "$(hcloud ssh-key describe "$key_name" -o json | jq -r '.labels.relay // empty')" = "deploy" ]; then
        log "Deleting SSH key $key_name"
        hcloud ssh-key delete "$key_name"
    else
        log "SSH key $key_name is not managed by relay, skipping"
    fi
done

if [ "${DELETE_BUCKET:-0}" = "1" ]; then
    log "Deleting bucket $S3_BUCKET"
    if aws --endpoint-url "$S3_ENDPOINT_URL" s3api head-bucket --bucket "$S3_BUCKET" >/dev/null 2>&1; then
        aws --endpoint-url "$S3_ENDPOINT_URL" s3 rb "s3://$S3_BUCKET" --force
    else
        log "Bucket $S3_BUCKET does not exist"
    fi
fi

cat <<EOF

Teardown complete. The GitHub variables and secrets still reference the old
server. Remove them with:

  gh variable delete SSH_HOSTNAME
  gh variable delete SSH_KNOWN_HOSTS
  gh variable delete HOSTNAME --env production
EOF
