#!/usr/bin/env bash

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")" || exit 1
source config.sh

ACCESS_DIR="${ACCESS_DIR:-$STATE_DIR/access}"
ACCESS_LABEL="relay-access/collaborator"
TOKEN_TTL="${TOKEN_TTL:-8760h}"
TOKEN_REFRESH_SECONDS="${TOKEN_REFRESH_SECONDS:-2592000}"

require_env GH_TOKEN GITHUB_REPOSITORY KUBECONFIG
require_command age gh kubectl python3

mkdir -p "$ACCESS_DIR"

SCRATCH="$(mktemp -d)"
trap 'rm -rf "$SCRATCH"' EXIT

CLUSTER_SERVER="$(kubectl config view --minify -o jsonpath='{.clusters[0].cluster.server}')"
CLUSTER_CA="$(kubectl config view --raw --minify -o jsonpath='{.clusters[0].cluster.certificate-authority-data}')"
[ -n "$CLUSTER_SERVER" ] && [ -n "$CLUSTER_CA" ] ||
fail "the kubeconfig carries no server address or CA, so no collaborator kubeconfig can be written"

apply_service_account() {
    kubectl apply -f - <<EOF
apiVersion: v1
kind: ServiceAccount
metadata:
  name: $1
  labels:
    $ACCESS_LABEL: $1
EOF
}

service_account_token() {
    local sa="$1" token="" exp=0
    token="$(kubectl get secret "$sa-token" \
        -o go-template='{{index .data "token" | base64decode}}' 2>/dev/null || true)"
    if [ -n "$token" ]; then
        exp="$(printf '%s' "$token" | python3 -c 'import base64,json,sys; p=sys.stdin.read().split(".")[1]; print(json.loads(base64.urlsafe_b64decode(p+"="*(-len(p)%4))).get("exp",0))' 2>/dev/null || printf '0')"
    fi
    if [ "$exp" -gt "$(( $(date +%s) + TOKEN_REFRESH_SECONDS ))" ]; then
        printf '%s' "$token"
        return
    fi
    token="$(kubectl create token "$sa" --duration="$TOKEN_TTL")" || return 1
    kubectl delete secret "$sa-token" --ignore-not-found >/dev/null
    kubectl apply -f - >/dev/null <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: $sa-token
  labels:
    $ACCESS_LABEL: $sa
type: Opaque
stringData:
  token: "$token"
EOF
    printf '%s' "$token"
}

write_kubeconfig() {
    cat > "$2" <<EOF
apiVersion: v1
kind: Config
clusters:
  - name: relay
    cluster:
      server: $CLUSTER_SERVER
      certificate-authority-data: $CLUSTER_CA
contexts:
  - name: relay
    context:
      cluster: relay
      user: $1
current-context: relay
users:
  - name: $1
    user:
      token: $3
EOF
}

gh api "repos/$GITHUB_REPOSITORY/collaborators" --paginate --jq '.[].login' > "$SCRATCH/collaborators"
[ -s "$SCRATCH/collaborators" ] ||
fail "the collaborator list came back empty, so nothing would be issued and every credential would be revoked"

: > "$SCRATCH/current"

while read -r login; do
    # Prefixed, so a login cannot adopt the deploy or dozzle ServiceAccount.
    sa="relay-access-$(printf '%s' "$login" | tr '[:upper:]' '[:lower:]')"
    printf '%s\n' "$sa" >> "$SCRATCH/current"
    recipients="$SCRATCH/recipients-$sa"
    gh api "users/$login/keys" --paginate --jq '.[].key' |
    awk '$1 == "ssh-ed25519" || $1 == "ssh-rsa" {print $1, $2}' > "$recipients"
    if [ ! -s "$recipients" ]; then
        echo "::notice::$login has no SSH key on GitHub that age can encrypt to, so no credential is issued for them"
        continue
    fi
    apply_service_account "$sa"
    # Checked here, because errexit does not reach into a command substitution.
    token="$(service_account_token "$sa")" ||
    fail "no token for $sa, so no credential is issued for $login"
    write_kubeconfig "$sa" "$SCRATCH/kubeconfig-$login" "$token"
    age --encrypt --recipients-file "$recipients" \
        --output "$ACCESS_DIR/$login-kubeconfig.age" "$SCRATCH/kubeconfig-$login"
    note "issued $login"
done < "$SCRATCH/collaborators"

while read -r stale; do
    [ -n "$stale" ] || continue
    grep -qx "$stale" "$SCRATCH/current" && continue
    kubectl delete serviceaccount,secret -l "$ACCESS_LABEL=$stale" --ignore-not-found
    note "removed $stale"
    done < <(kubectl get serviceaccount -l "$ACCESS_LABEL" \
    -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}')
