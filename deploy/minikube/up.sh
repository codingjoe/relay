#!/usr/bin/env bash
#
# Run the production stack on minikube.
#
# Needs docker, minikube, kubectl, dotenvx and envsubst, and an
# .env.production with its .env.keys beside it.
#
# RELAY_LOCAL_HOSTNAME  the local name in /etc/hosts (default relay.local)
# RELAY_SKIP_BUILD=1    keep the image that minikube already has
# RELAY_ENV_FILE        another environment file to read the values from

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${RELAY_ENV_FILE:-$REPO_ROOT/.env.production}"
KEYS_FILE="$(dirname "$ENV_FILE")/.env.keys"
MAIN_CHECKOUT="$(dirname "$(git -C "$REPO_ROOT" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)" 2>/dev/null || true)"
NAMESPACE=relay
LOCAL_HOSTNAME="${RELAY_LOCAL_HOSTNAME:-relay.local}"
STORAGE_HOSTNAME="storage.$LOCAL_HOSTNAME"
CERTIFICATES=/data/caddy/certificates/local
IMAGE=ghcr.io/codingjoe/relay:local

note() {
    printf '    %s\n' "$*"
}

fail() {
    printf 'error: %s\n' "$*" >&2
    exit 1
}

value() {
    dotenvx get "$1" -f "$ENV_FILE"
}

for tool in docker minikube kubectl dotenvx envsubst; do
    command -v "$tool" >/dev/null 2>&1 || fail "$tool is not installed"
done
[ -f "$ENV_FILE" ] || fail "$ENV_FILE is missing"
if [ ! -f "$KEYS_FILE" ]; then
    if [ -n "$MAIN_CHECKOUT" ] && [ "$MAIN_CHECKOUT" != "$REPO_ROOT" ] && [ -f "$MAIN_CHECKOUT/.env.keys" ]; then
        fail "$KEYS_FILE is missing. Run this script from $MAIN_CHECKOUT."
    fi
    fail "$KEYS_FILE is missing, so $ENV_FILE cannot be decrypted"
fi

note "Start minikube"
minikube status >/dev/null 2>&1 || minikube start

if [ "${RELAY_SKIP_BUILD:-0}" != 1 ]; then
    note "Build $IMAGE"
    docker build --target production --build-arg UV_NO_DEV=0 -t "$IMAGE" "$REPO_ROOT"
    minikube image load "$IMAGE"
fi

note "Create the namespace and the Secrets"
kubectl create namespace "$NAMESPACE" --dry-run=client --output=yaml | kubectl apply -f - >/dev/null

postgres_password="$(value POSTGRES_PASSWORD)"
redis_password="$(value REDIS_PASSWORD)"
rspamd_password="$(value RELAY_RSPAMD_PASSWORD)"
private_key="$(dotenvx get DOTENV_PRIVATE_KEY_PRODUCTION -f "$KEYS_FILE")"
[ -n "$postgres_password" ] || fail "POSTGRES_PASSWORD is empty in $ENV_FILE"
[ -n "$redis_password" ] || fail "REDIS_PASSWORD is empty in $ENV_FILE"
[ -n "$rspamd_password" ] || fail "RELAY_RSPAMD_PASSWORD is empty in $ENV_FILE"
[ -n "$private_key" ] || fail "DOTENV_PRIVATE_KEY_PRODUCTION is empty in $KEYS_FILE"

kubectl create secret generic dotenvx-key --namespace "$NAMESPACE" \
    --from-literal=DOTENV_PRIVATE_KEY_PRODUCTION="$private_key" \
    --dry-run=client --output=yaml | kubectl apply -f - >/dev/null

kubectl create secret generic relay-infra --namespace "$NAMESPACE" \
    --from-literal=HOSTNAME="$LOCAL_HOSTNAME" \
    --from-literal=RELAY_STORAGE_DOMAIN="$STORAGE_HOSTNAME" \
    --from-literal=POSTGRES_PASSWORD="$postgres_password" \
    --from-literal=REDIS_PASSWORD="$redis_password" \
    --from-literal=RELAY_RSPAMD_PASSWORD="$rspamd_password" \
    --dry-run=client --output=yaml | kubectl apply -f - >/dev/null

kubectl create secret generic relay-cluster-env --namespace "$NAMESPACE" \
    --from-literal=DATABASE_URL="postgresql://postgres:${postgres_password}@postgres:5432/postgres" \
    --from-literal=REDIS_URL="redis://:${redis_password}@redis:6379/0" \
    --from-literal=TASK_REDIS_URL="redis://:${redis_password}@redis-tasks:6379/0" \
    --from-literal=RELAY_RSPAMD_URL="http://:${rspamd_password}@rspamd:11334" \
    --from-literal=RELAY_SMTP_TLS_CERT_PATH="${CERTIFICATES}/smtp.${LOCAL_HOSTNAME}/smtp.${LOCAL_HOSTNAME}.crt" \
    --from-literal=RELAY_SMTP_TLS_KEY_PATH="${CERTIFICATES}/smtp.${LOCAL_HOSTNAME}/smtp.${LOCAL_HOSTNAME}.key" \
    --from-literal=RELAY_MX_TLS_CERT_PATH="${CERTIFICATES}/mx1.${LOCAL_HOSTNAME}/mx1.${LOCAL_HOSTNAME}.crt,${CERTIFICATES}/mx2.${LOCAL_HOSTNAME}/mx2.${LOCAL_HOSTNAME}.crt" \
    --from-literal=RELAY_MX_TLS_KEY_PATH="${CERTIFICATES}/mx1.${LOCAL_HOSTNAME}/mx1.${LOCAL_HOSTNAME}.key,${CERTIFICATES}/mx2.${LOCAL_HOSTNAME}/mx2.${LOCAL_HOSTNAME}.key" \
    --dry-run=client --output=yaml | kubectl apply -f - >/dev/null

note "Render the rspamd and redis configuration"
rendered="$(mktemp -d)"
trap 'rm -rf "$rendered"' EXIT
mkdir -p "$rendered/rspamd" "$rendered/redis"
for file in "$REPO_ROOT"/deploy/k8s/rspamd/*; do
    name="$(basename "$file")"
    dotenvx run -f "$ENV_FILE" -- envsubst <"$file" >"$rendered/rspamd/$name"
done
for file in "$REPO_ROOT"/deploy/k8s/redis/*; do
    name="$(basename "$file")"
    dotenvx run -f "$ENV_FILE" -- envsubst <"$file" >"$rendered/redis/$name"
done
kubectl create secret generic rspamd-config --namespace "$NAMESPACE" \
    --from-file="$rendered/rspamd/" --dry-run=client --output=yaml | kubectl apply -f - >/dev/null
kubectl create secret generic redis-config --namespace "$NAMESPACE" \
    --from-file="$rendered/redis/" --dry-run=client --output=yaml | kubectl apply -f - >/dev/null

note "Apply the manifests"
kubectl apply -f "$REPO_ROOT/deploy/k8s/dozzle-rbac.yaml" >/dev/null
kubectl apply -k "$REPO_ROOT/deploy/minikube" >/dev/null

note "Wait for the web rollout"
kubectl rollout status --namespace "$NAMESPACE" deployment/web --timeout=10m

cat <<EOF

Add this line to /etc/hosts:

  $(minikube ip) $LOCAL_HOSTNAME $STORAGE_HOSTNAME

Then open https://$LOCAL_HOSTNAME.

For the log dashboard, run:

  kubectl --namespace $NAMESPACE port-forward svc/dozzle 5000:8080
EOF
