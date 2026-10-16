#!/usr/bin/env bash
#
# Provisioning step: hand the deployment to GitHub Actions and write the
# production environment file.
#
# Inputs: RELAY_HOSTNAME, TALOS_DIR, TALOS_INSTALLER, S3_BUCKET.
#         AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY come from the environment
#         on the first provisioning, and from .env.production after that.

set -euo pipefail

STEPS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../config.sh
source "$(dirname "$STEPS_DIR")/config.sh"
# shellcheck source=../hcloud.sh
source "$DEPLOY_DIR/hcloud.sh"

TALOSCONFIG_FILE="$TALOS_DIR/talosconfig"
KUBECONFIG_FILE="$TALOS_DIR/kubeconfig"
# The cluster identity the two GitHub secrets were last published for, so a
# rebuild from new secrets cannot leave a stale credential in place.
IDENTITY_FILE="$TALOS_DIR/published-ca.sha256"
# The node's certificate covers its own name and its addresses, and the platform
# truncates a server name at the first dot, so a client that dials
# $RELAY_HOSTNAME fails the handshake. The workflows hand this to talosctl -n.
TALOS_ENDPOINT="$(fetch_server_address)"

environment_is_set() {
    local secrets server_address smtp_addresses smtp_source_addresses
    server_address="$(fetch_server_address)"
    [ -n "$server_address" ] || return 1
    read -ra smtp_addresses <<<"$(fetch_smtp_floating_ip_addresses)"
    [ -n "${smtp_addresses[0]:-}" ] || return 1
    smtp_source_addresses="$(comma_list "${smtp_addresses[@]}"),$server_address"
    # The pool is bound by the machine config and advertised by the mail
    # records, so a pool that changed since the last run has to publish again.
    [ "$(dotenvx get RELAY_DNS_SMTP_IPS -f "$REPO_ROOT/.env.production" 2>/dev/null)" = "$smtp_source_addresses" ] || return 1
    [ "$(dotenvx get RELAY_SMTP_SOURCE_IPS -f "$REPO_ROOT/.env.production" 2>/dev/null)" = "$smtp_source_addresses" ] || return 1
    [ "$(gh variable get HOSTNAME --env production 2>/dev/null)" = "$RELAY_HOSTNAME" ] || return 1
    [ "$(gh variable get TALOS_ENDPOINT 2>/dev/null)" = "$TALOS_ENDPOINT" ] || return 1
    [ "$(gh variable get TALOS_INSTALLER 2>/dev/null)" = "$TALOS_INSTALLER" ] || return 1
    secrets="$(gh secret list 2>/dev/null || true)"
    printf '%s\n' "$secrets" | grep -q "^KUBECONFIG" || return 1
    printf '%s\n' "$secrets" | grep -q "^TALOSCONFIG" || return 1
    printf '%s\n' "$secrets" | grep -q "^DOTENV_PRIVATE_KEY_PRODUCTION" || return 1
    # Present is not the same as current. A rebuild from a new secrets bundle
    # leaves both secrets in place while the cluster stops trusting them, and
    # the deploy then dies on "certificate signed by unknown authority".
    published_credentials_are_current || return 1
    [ "$(dotenvx get HOSTNAME -f "$REPO_ROOT/.env.production" 2>/dev/null)" = "$RELAY_HOSTNAME" ] || return 1
    [ "$(dotenvx get RELAY_STORAGE_DOMAIN -f "$REPO_ROOT/.env.production" 2>/dev/null)" = "$STORAGE_HOSTNAME" ] || return 1
    [ "$(dotenvx get AWS_S3_ENDPOINT_URL -f "$REPO_ROOT/.env.production" 2>/dev/null)" = "$S3_ENDPOINT_URL" ] || return 1
    [ "$(dotenvx get AWS_STORAGE_BUCKET_NAME -f "$REPO_ROOT/.env.production" 2>/dev/null)" = "$S3_BUCKET" ] || return 1
}

kubectl_admin() {
    kubectl --kubeconfig "$KUBECONFIG_FILE" "$@"
}

talos_api_is_reachable() {
    talosctl --talosconfig "$TALOSCONFIG_FILE" version --short >/dev/null 2>&1
}

cluster_is_ready() {
    [ -n "$(kubectl_admin get secret deploy-token -o jsonpath='{.data.token}' 2>/dev/null)" ]
}

# The cluster's identity, as the deploy token carries it: the CA it trusts. A
# rerun that keeps the secrets bundle reinstalls the node onto the same PKI and
# this does not move; deleting deploy/.state mints a new one.
cluster_identity() {
    kubectl_admin get secret deploy-token -o jsonpath='{.data.ca\.crt}' 2>/dev/null |
    python3 -c 'import hashlib, sys
data = sys.stdin.read().strip()
print(hashlib.sha256(data.encode()).hexdigest() if data else "")'
}

# The two secrets carry a Role and a client certificate from one cluster, so
# both are republished together and one fingerprint covers them both.
published_credentials_are_current() {
    local recorded current
    recorded="$(cat "$IDENTITY_FILE" 2>/dev/null)" || return 1
    [ -n "$recorded" ] || return 1
    current="$(cluster_identity)"
    [ -n "$current" ] || return 1
    [ "$current" = "$recorded" ]
}

deploy_kubeconfig() {
    local token certificate_authority server
    token="$(kubectl_admin get secret deploy-token -o jsonpath='{.data.token}' |
        python3 -c 'import base64, sys; print(base64.b64decode(sys.stdin.read().strip()).decode())')"
    [ -n "$token" ] || return 1
    certificate_authority="$(kubectl_admin get secret deploy-token -o jsonpath='{.data.ca\.crt}')"
    [ -n "$certificate_authority" ] || return 1
    server="$(kubectl_admin config view --minify -o jsonpath='{.clusters[0].cluster.server}')"
    [ -n "$server" ] || return 1
    cat <<EOF
apiVersion: v1
kind: Config
clusters:
  - name: relay
    cluster:
      server: $server
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

require_command gh dotenvx openssl python3 talosctl kubectl
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

[ -f "$TALOSCONFIG_FILE" ] ||
fail "$TALOSCONFIG_FILE is missing. Run ./deploy/provision.sh keys first"

# The keys step tightens TALOS_DIR, but a run of this step alone cannot rely
# on it: the talosconfig and kubeconfig here are cluster credentials.
umask 077
chmod 700 "$TALOS_DIR"
for file in "$TALOSCONFIG_FILE" "$KUBECONFIG_FILE"; do
    [ -f "$file" ] || continue
    chmod 600 "$file"
done

SERVER_ADDRESS="$(fetch_server_address)"
[ -n "$SERVER_ADDRESS" ] ||
fail "no server named $RELAY_HOSTNAME. Run ./deploy/provision.sh server first"

read -ra smtp_addresses <<<"$(fetch_smtp_floating_ip_addresses)"
[ -n "${smtp_addresses[0]:-}" ] ||
fail "no SMTP floating IPs found. Run ./deploy/provision.sh egress first"

SMTP_FLOATING_IP_ADDRESSES="$(comma_list "${smtp_addresses[@]}")"
SMTP_SOURCE_ADDRESSES="$SMTP_FLOATING_IP_ADDRESSES,$SERVER_ADDRESS"

note "Waiting for the Talos API on $TALOS_ENDPOINT"
if ! wait_until "the Talos API on $TALOS_ENDPOINT" talos_api_is_reachable; then
    warn "the node does not answer on the Talos API yet. A freshly created node has to finish its first boot; if it never does, read it:"
    warn "  talosctl --talosconfig $TALOSCONFIG_FILE dmesg"
    warn "  hcloud server describe $RELAY_HOSTNAME"
    warn "Otherwise, run this step again once the node answers."
    exit "$EXIT_INCOMPLETE"
fi

note "Writing $KUBECONFIG_FILE from the node"
# --merge=false: the file is exactly the admin kubeconfig the node serves, not
# a merge into one that a previous cluster left behind.
talosctl --talosconfig "$TALOSCONFIG_FILE" kubeconfig --force --merge=false "$KUBECONFIG_FILE"

note "Waiting for the cluster on $SERVER_ADDRESS"
if ! wait_until "the deploy token" cluster_is_ready; then
    warn "the Kubernetes API is not serving the deploy token yet. If the cluster has not been bootstrapped, bootstrap it once:"
    warn "  talosctl --talosconfig $TALOSCONFIG_FILE bootstrap"
    warn "If it has, read what this boot did:"
    warn "  talosctl --talosconfig $TALOSCONFIG_FILE dmesg"
    warn "  kubectl --kubeconfig $KUBECONFIG_FILE get pods -A"
    warn "Otherwise, run this step again once the install has finished."
    exit "$EXIT_INCOMPLETE"
fi

note "Writing variables and secrets to GitHub"
gh variable set HOSTNAME --body "$RELAY_HOSTNAME" --env production
gh variable set TALOS_ENDPOINT --body "$TALOS_ENDPOINT"
gh variable set TALOS_INSTALLER --body "$TALOS_INSTALLER"
# The SSH pair left with sync-ssh-keys.yml; delete what earlier runs published.
# A missing one is not an error.
gh variable delete SSH_HOSTNAME 2>/dev/null || true
gh variable delete SSH_KNOWN_HOSTS 2>/dev/null || true
gh secret delete SSH_PRIVATE_KEY 2>/dev/null || true
# Through stdin, not --body: an argument is readable by any local user in
# /proc/<pid>/cmdline, and these two are the cluster credentials.
deploy_kubeconfig | gh secret set KUBECONFIG
gh secret set TALOSCONFIG <"$TALOSCONFIG_FILE"
# gh secret set overwrites, so a stale pair is replaced rather than refused, and
# this records which cluster they were published for.
identity="$(cluster_identity)"
[ -n "$identity" ] ||
fail "the deploy token carries no CA, so the published credentials cannot be identified"
printf '%s\n' "$identity" >"$IDENTITY_FILE"

note "Keep $TALOS_DIR/secrets.yaml: it reissues the TALOSCONFIG credential and is the cluster recovery input."

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

# The signing key is the one secret that is not a random token, so it stays out
# of the loop above: the MCP OIDC provider needs an RSA-2048 PEM. Keep an
# existing key, because rotating it invalidates every access token already
# issued and the web pod republishes its JWKS only on the next start.
if dotenvx get RELAY_MCP_OIDC_PRIVATE_KEY -f .env.production >/dev/null 2>&1; then
    note "RELAY_MCP_OIDC_PRIVATE_KEY is already set, leaving it alone"
else
    dotenvx set RELAY_MCP_OIDC_PRIVATE_KEY "$(openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048)" -f .env.production
fi

gh secret set DOTENV_PRIVATE_KEY_PRODUCTION --body "$(dotenvx get DOTENV_PRIVATE_KEY_PRODUCTION -f .env.keys)"

cat <<EOF

Commit the encrypted environment file:

  git add .env.production
  git commit -m "Update production environment for $RELAY_HOSTNAME"
  git push
EOF

save_state "SMTP_FLOATING_IP_ADDRESSES=$SMTP_FLOATING_IP_ADDRESSES" \
    "SMTP_SOURCE_ADDRESSES=$SMTP_SOURCE_ADDRESSES" \
    "S3_BUCKET=$S3_BUCKET"
record_step environment "published GitHub variables and secrets for $SERVER_ADDRESS"

note "Next: gh workflow run deploy.yml"
