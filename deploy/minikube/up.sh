#!/usr/bin/env bash
#
# Run the production stack on minikube with the local .env.
#
# Needs docker, minikube, kubectl, dotenvx and envsubst, and a .env in the
# checkout you run from. The script bakes that file into the image, so run it
# again after you change a value.
#
# RELAY_SKIP_BUILD=1  keep the images that minikube already has
# RELAY_ENV_FILE      another environment file to read

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${RELAY_ENV_FILE:-$REPO_ROOT/.env}"
NAMESPACE=relay
IMAGE=ghcr.io/codingjoe/relay:local
BASE_IMAGE=ghcr.io/codingjoe/relay:local-base
CERTIFICATES=/data/caddy/certificates/local

note() {
    printf '    %s\n' "$*"
}

warn() {
    printf 'warning: %s\n' "$*" >&2
}

fail() {
    printf 'error: %s\n' "$*" >&2
    exit 1
}

value() {
    dotenvx get "$1" -f "$ENV_FILE" 2>/dev/null || true
}

context=""
rendered=""
cleanup() {
    [ -n "$context" ] && rm -rf "$context"
    [ -n "$rendered" ] && rm -rf "$rendered"
    return 0
}
trap cleanup EXIT

for tool in docker minikube kubectl dotenvx envsubst; do
    command -v "$tool" >/dev/null 2>&1 || fail "$tool is not installed"
done
[ -f "$ENV_FILE" ] || fail "$ENV_FILE is missing"

hostname="$(value HOSTNAME)"
[ -n "$hostname" ] || hostname=localhost
storage_domain="$(value RELAY_STORAGE_DOMAIN)"
[ -n "$storage_domain" ] || storage_domain="storage.$hostname"
postgres_password="$(value POSTGRES_PASSWORD)"
[ -n "$postgres_password" ] || postgres_password=postgres
redis_password="$(value REDIS_PASSWORD)"
[ -n "$redis_password" ] || redis_password=redis
rspamd_password="$(value RELAY_RSPAMD_PASSWORD)"
[ -n "$rspamd_password" ] || rspamd_password="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"

note "Start minikube"
minikube status >/dev/null 2>&1 || minikube start

if [ "${RELAY_SKIP_BUILD:-0}" != 1 ]; then
    note "Build $BASE_IMAGE"
    docker build --target production --build-arg UV_NO_DEV=0 -t "$BASE_IMAGE" "$REPO_ROOT"
    note "Add $ENV_FILE to $IMAGE"
    context="$(mktemp -d)"
    cp "$ENV_FILE" "$context/.env"
    cat >"$context/Dockerfile" <<EOF
FROM $BASE_IMAGE
COPY .env /app/.env
ENTRYPOINT ["dotenvx", "run", "-f", "/app/.env", "--", "/opt/venv/bin/python"]
EOF
    docker build --tag "$IMAGE" "$context"
    minikube image load "$IMAGE"
fi

note "Create the namespace and the Secrets"
kubectl create namespace "$NAMESPACE" --dry-run=client --output=yaml | kubectl apply -f - >/dev/null

# The manifests mount this Secret. The local image reads .env, so it holds no key.
kubectl create secret generic dotenvx-key --namespace "$NAMESPACE" \
    --from-literal=DOTENV_PRIVATE_KEY_PRODUCTION=local \
    --dry-run=client --output=yaml | kubectl apply -f - >/dev/null

infra_args=()
required_keys="$(grep -rhoE 'name: relay-infra, key: [A-Z0-9_]+' "$REPO_ROOT/deploy/k8s" | grep -oE '[A-Z0-9_]+$' | sort -u)"
while read -r key; do
    [ -n "$key" ] || continue
    case "$key" in
        HOSTNAME) secret_value="$hostname" ;;
        RELAY_STORAGE_DOMAIN) secret_value="$storage_domain" ;;
        POSTGRES_PASSWORD) secret_value="$postgres_password" ;;
        REDIS_PASSWORD) secret_value="$redis_password" ;;
        RELAY_RSPAMD_PASSWORD) secret_value="$rspamd_password" ;;
        *) secret_value="$(value "$key")" ;;
    esac
    [ -n "$secret_value" ] || warn "$key is not set in $ENV_FILE"
    infra_args+=("--from-literal=$key=$secret_value")
done <<<"$required_keys"
kubectl create secret generic relay-infra --namespace "$NAMESPACE" \
    "${infra_args[@]}" --dry-run=client --output=yaml | kubectl apply -f - >/dev/null

# The last envFrom wins, so these Service names beat the localhost URLs in .env.
kubectl create secret generic relay-cluster-env --namespace "$NAMESPACE" \
    --from-literal=DATABASE_URL="postgresql://postgres:${postgres_password}@postgres:5432/postgres" \
    --from-literal=REDIS_URL="redis://:${redis_password}@redis:6379/0" \
    --from-literal=TASK_REDIS_URL="redis://:${redis_password}@redis-tasks:6379/0" \
    --from-literal=RELAY_RSPAMD_URL="http://:${rspamd_password}@rspamd:11334" \
    --from-literal=RELAY_SMTP_TLS_CERT_PATH="${CERTIFICATES}/smtp.${hostname}/smtp.${hostname}.crt" \
    --from-literal=RELAY_SMTP_TLS_KEY_PATH="${CERTIFICATES}/smtp.${hostname}/smtp.${hostname}.key" \
    --from-literal=RELAY_MX_TLS_CERT_PATH="${CERTIFICATES}/mx1.${hostname}/mx1.${hostname}.crt,${CERTIFICATES}/mx2.${hostname}/mx2.${hostname}.crt" \
    --from-literal=RELAY_MX_TLS_KEY_PATH="${CERTIFICATES}/mx1.${hostname}/mx1.${hostname}.key,${CERTIFICATES}/mx2.${hostname}/mx2.${hostname}.key" \
    --dry-run=client --output=yaml | kubectl apply -f - >/dev/null

note "Render the rspamd and redis configuration"
rendered="$(mktemp -d)"
mkdir -p "$rendered/rspamd" "$rendered/redis"
for file in "$REPO_ROOT"/deploy/k8s/rspamd/*; do
    name="$(basename "$file")"
    REDIS_PASSWORD="$redis_password" RELAY_RSPAMD_PASSWORD="$rspamd_password" \
        dotenvx run -f "$ENV_FILE" -- envsubst <"$file" >"$rendered/rspamd/$name"
done
for file in "$REPO_ROOT"/deploy/k8s/redis/*; do
    name="$(basename "$file")"
    REDIS_PASSWORD="$redis_password" dotenvx run -f "$ENV_FILE" -- envsubst <"$file" >"$rendered/redis/$name"
done
kubectl create secret generic rspamd-config --namespace "$NAMESPACE" \
    --from-file="$rendered/rspamd/" --dry-run=client --output=yaml | kubectl apply -f - >/dev/null
kubectl create secret generic redis-config --namespace "$NAMESPACE" \
    --from-file="$rendered/redis/" --dry-run=client --output=yaml | kubectl apply -f - >/dev/null

note "Apply the manifests"
kubectl delete job --namespace "$NAMESPACE" --ignore-not-found migration clamav-updater >/dev/null
kubectl apply -f "$REPO_ROOT/deploy/k8s/dozzle-rbac.yaml" >/dev/null
kubectl apply -k "$REPO_ROOT/deploy/minikube" >/dev/null

note "Wait for the migration"
kubectl wait --namespace "$NAMESPACE" --for=condition=complete job/migration --timeout=10m

note "Wait for the web rollout"
kubectl rollout status --namespace "$NAMESPACE" deployment/web --timeout=10m

if [ "$hostname" = localhost ]; then
    address=http://localhost:8000
else
    address="http://$hostname:8000"
    printf '\nAdd this line to /etc/hosts:\n\n  127.0.0.1 %s\n' "$hostname"
fi

cat <<EOF

The stack is up. Run this port-forward in another terminal:

  kubectl --namespace $NAMESPACE port-forward svc/web 8000:8000

Then open $address.

For the log dashboard:

  kubectl --namespace $NAMESPACE port-forward svc/dozzle 5000:8080
EOF
