#!/usr/bin/env bash
#
# Provisioning step: hand the deployment to GitHub Actions and write the
# production environment file.
#
# Inputs: RELAY_HOSTNAME, DEPLOY_KEY, S3_BUCKET. AWS_ACCESS_KEY_ID and
#         AWS_SECRET_ACCESS_KEY come from the environment on the first
#         provisioning, and from .env.production after that.

set -euo pipefail

STEPS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../config.sh
source "$(dirname "$STEPS_DIR")/config.sh"
# shellcheck source=../hcloud.sh
source "$DEPLOY_DIR/hcloud.sh"

environment_is_set() {
    local address secrets
    address="$(fetch_server_address)"
    [ -n "$address" ] || return 1
    [ "$(gh variable get SSH_HOSTNAME 2>/dev/null)" = "$address" ] || return 1
    [ "$(gh variable get HOSTNAME --env production 2>/dev/null)" = "$RELAY_HOSTNAME" ] || return 1
    secrets="$(gh secret list 2>/dev/null || true)"
    printf '%s\n' "$secrets" | grep -q "^KUBECONFIG" || return 1
    printf '%s\n' "$secrets" | grep -q "^SSH_PRIVATE_KEY" || return 1
    printf '%s\n' "$secrets" | grep -q "^DOTENV_PRIVATE_KEY_PRODUCTION" || return 1
    [ "$(dotenvx get HOSTNAME -f "$REPO_ROOT/.env.production" 2>/dev/null)" = "$RELAY_HOSTNAME" ] || return 1
    [ "$(dotenvx get RELAY_STORAGE_DOMAIN -f "$REPO_ROOT/.env.production" 2>/dev/null)" = "$STORAGE_HOSTNAME" ] || return 1
    [ "$(dotenvx get AWS_S3_ENDPOINT_URL -f "$REPO_ROOT/.env.production" 2>/dev/null)" = "$S3_ENDPOINT_URL" ] || return 1
    [ "$(dotenvx get AWS_STORAGE_BUCKET_NAME -f "$REPO_ROOT/.env.production" 2>/dev/null)" = "$S3_BUCKET" ] || return 1
}

ssh_is_reachable() {
    [ -n "$(ssh-keyscan -T 5 "$1" 2>/dev/null)" ]
}

ssh_deploy() {
    ssh -i "$DEPLOY_KEY" \
        -o "UserKnownHostsFile=$KNOWN_HOSTS_FILE" \
        -o StrictHostKeyChecking=yes \
        -o BatchMode=yes \
        -o ConnectTimeout=10 \
        "github@$SERVER_ADDRESS" "$@"
}

cluster_is_ready() {
    ssh_deploy "sudo k3s kubectl -n $RELAY_NAMESPACE get secret deploy-token" >/dev/null 2>&1
}

deploy_kubeconfig() {
    local token certificate_authority
    token="$(ssh_deploy "sudo k3s kubectl -n $RELAY_NAMESPACE get secret deploy-token -o jsonpath='{.data.token}'" |
        python3 -c 'import base64, sys; print(base64.b64decode(sys.stdin.read().strip()).decode())')"
    [ -n "$token" ] || return 1
    certificate_authority="$(ssh_deploy "sudo k3s kubectl -n $RELAY_NAMESPACE get secret deploy-token -o jsonpath='{.data.ca\.crt}'")"
    [ -n "$certificate_authority" ] || return 1
    cat <<EOF
apiVersion: v1
kind: Config
clusters:
  - name: relay
    cluster:
      server: https://$SERVER_ADDRESS:6443
      certificate-authority-data: $certificate_authority
contexts:
  - name: relay
    context:
      cluster: relay
      user: deploy
current-context: relay
users:
  - name: deploy
    user:
      token: $token
EOF
}

if [ "${1:-}" = "--check" ]; then
    environment_is_set
    exit "$?"
fi

require_command gh dotenvx python3 ssh-keyscan
adopt_stored_s3_credentials
require_env AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY

if environment_is_set; then
    confirm_step environment "the repository variables and .env.production are set"
fi

# .env.production is committed in encrypted form, so the private key that
# decrypts it has to be here before anything is published. It is git-ignored
# and lives outside the repository.
[ -f "$REPO_ROOT/.env.keys" ] ||
fail ".env.keys is missing, so .env.production cannot be written. Restore the key that decrypts .env.production, or re-encrypt the file with a new key pair, then run ./deploy/provision.sh environment"

SERVER_ADDRESS="$(fetch_server_address)"
[ -n "$SERVER_ADDRESS" ] ||
fail "no server named $RELAY_HOSTNAME. Run ./deploy/provision.sh server first"

read -ra smtp_addresses <<<"$(fetch_smtp_floating_ip_addresses)"
[ -n "${smtp_addresses[0]:-}" ] ||
fail "no SMTP floating IPs found. Run ./deploy/provision.sh egress first"

SMTP_FLOATING_IP_ADDRESSES="$(comma_list "${smtp_addresses[@]}")"
SMTP_SOURCE_ADDRESSES="$SMTP_FLOATING_IP_ADDRESSES,$SERVER_ADDRESS"

KNOWN_HOSTS_FILE="$(mktemp)"
trap 'rm -f "$KNOWN_HOSTS_FILE"' EXIT

note "Waiting for SSH on $SERVER_ADDRESS"
if ! wait_until "SSH on $SERVER_ADDRESS" ssh_is_reachable "$SERVER_ADDRESS"; then
    warn "the server does not answer on SSH yet. Run this step again once it does."
    exit "$EXIT_INCOMPLETE"
fi

SSH_KNOWN_HOSTS="$(ssh-keyscan -T 5 "$SERVER_ADDRESS" 2>/dev/null)"
printf '%s\n' "$SSH_KNOWN_HOSTS" >"$KNOWN_HOSTS_FILE"

note "Waiting for the cluster on $SERVER_ADDRESS"
if ! wait_until "the relay namespace and deploy token" cluster_is_ready; then
    warn "k3s is not serving the relay namespace yet. Check cloud-init on the server, then run this step again."
    exit "$EXIT_INCOMPLETE"
fi

note "Writing variables and secrets to GitHub"
gh variable set SSH_HOSTNAME --body "$SERVER_ADDRESS"
gh variable set SSH_KNOWN_HOSTS --body "$SSH_KNOWN_HOSTS"
gh variable set HOSTNAME --body "$RELAY_HOSTNAME" --env production
gh secret set SSH_PRIVATE_KEY <"$DEPLOY_KEY"
gh secret set KUBECONFIG --body "$(deploy_kubeconfig)"

note "Writing the infrastructure values to .env.production"
dotenvx set HOSTNAME "$RELAY_HOSTNAME" -f .env.production --plain
dotenvx set RELAY_STORAGE_DOMAIN "$STORAGE_HOSTNAME" -f .env.production --plain
dotenvx set RELAY_DNS_SMTP_IPS "$SMTP_SOURCE_ADDRESSES" -f .env.production --plain
dotenvx set RELAY_SMTP_SOURCE_IPS "$SMTP_SOURCE_ADDRESSES" -f .env.production --plain
dotenvx set AWS_S3_ENDPOINT_URL "$S3_ENDPOINT_URL" -f .env.production --plain
dotenvx set AWS_STORAGE_BUCKET_NAME "$S3_BUCKET" -f .env.production --plain
dotenvx set AWS_S3_REGION_NAME "$S3_REGION" -f .env.production --plain
dotenvx set AWS_S3_ADDRESSING_STYLE path -f .env.production --plain
dotenvx set AWS_S3_ACCESS_KEY_ID "$AWS_ACCESS_KEY_ID" -f .env.production
dotenvx set AWS_S3_SECRET_ACCESS_KEY "$AWS_SECRET_ACCESS_KEY" -f .env.production

for key in POSTGRES_PASSWORD REDIS_PASSWORD RELAY_RSPAMD_PASSWORD SECRET_KEY; do
    if dotenvx get "$key" -f .env.production >/dev/null 2>&1; then
        note "$key is already set, leaving it alone"
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

save_state "SSH_KNOWN_HOSTS=$SSH_KNOWN_HOSTS" \
    "SMTP_FLOATING_IP_ADDRESSES=$SMTP_FLOATING_IP_ADDRESSES" \
    "SMTP_SOURCE_ADDRESSES=$SMTP_SOURCE_ADDRESSES" \
    "S3_BUCKET=$S3_BUCKET"
record_step environment "published GitHub variables and secrets for $SERVER_ADDRESS"

note "Next: gh workflow run deploy.yml"
