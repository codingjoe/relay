#!/usr/bin/env bash
#
# Provisioning step: create the Talos server and assign the egress pool to it.
#
# The server boots the snapshot the image step uploaded, with the patched
# machine config as user_data: Talos reads it from the instance metadata,
# installs itself to disk and comes back as the cluster's only control plane,
# so etcd is bootstrapped here, once, and the kubeconfig is written for the
# steps and the deploy workflow that follow.
#
# Inputs: RELAY_HOSTNAME, SERVER_TYPE, SERVER_LOCATION, SMTP_FLOATING_IP_COUNT

set -euo pipefail

STEPS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../config.sh
source "$(dirname "$STEPS_DIR")/config.sh"
# shellcheck source=../hcloud.sh
source "$DEPLOY_DIR/hcloud.sh"

TALOSCTL=(talosctl --talosconfig "$TALOS_DIR/talosconfig")

# Run talosctl on the server hcloud reports: the checks below also run before
# the step has stored an address.
run_talosctl() {
    local address
    command -v talosctl >/dev/null 2>&1 || return 1
    address="$(fetch_server_address)"
    [ -n "$address" ] || return 1
    "${TALOSCTL[@]}" --nodes "$address" --endpoints "$address" "$@"
}

# A node in maintenance mode has no machine config to return, and a node that
# is still writing its disk answers nothing at all, so the config is the first
# thing that proves the boot from the image metadata was read and survived. The
# document is read rather than listed, so an empty answer cannot pass.
talos_is_configured() {
    local config
    # Captured, not piped: `grep -q` exits at the match and closes the pipe, and
    # the SIGPIPE that kills talosctl fails the pipeline under `pipefail`, so a
    # healthy node would read as unconfigured.
    config="$(run_talosctl get mc v1alpha1 -o yaml 2>/dev/null)" || return 1
    grep -q 'machine:' <<<"$config"
}

# The image tells a box that ran this step's first boot from one that predates
# it, because a Docker host has the same name, the same address and the same
# pool, and would otherwise be reported as done while it runs no Talos at all.
# An image hcloud cannot report is not a mismatch, so a box whose snapshot has
# since been deleted is not condemned by it.
server_image_is_expected() {
    local image_id
    image_id="$(fetch_server_image_id)"
    [ -z "$image_id" ] || [ "$image_id" = "$(talos_image_id)" ]
}

# A server that exists is not enough: it has to be the one this guide built,
# with the egress pool assigned and bound, Talos reading the machine config and
# etcd answering, or the sender cannot bind the addresses it sends from and the
# cluster has nothing to deploy into.
server_is_ready() {
    local index server_id address bound_addresses
    local -a pool
    server_id="$(fetch_server_id)"
    [ -n "$server_id" ] || return 1
    [ "$(fetch_server_status)" = "running" ] || return 1
    server_image_is_expected || return 1
    for ((index = 1; index <= SMTP_FLOATING_IP_COUNT; index++)); do
        [ "$(floating_ip_server_id "$(smtp_floating_ip_name "$index")")" = "$server_id" ] || return 1
    done
    talos_is_configured || return 1
    # hcloud answers who holds the pool; only the node answers what it bound. A
    # pool grown while the node kept its old link config is assigned in hcloud
    # and unbound on the node, so a rerun cannot confirm the step on the
    # assignment alone: without these addresses it applies the machine config
    # again below.
    read -ra pool <<<"$(fetch_smtp_floating_ip_addresses)"
    [ "${#pool[@]}" -eq "$SMTP_FLOATING_IP_COUNT" ] || return 1
    bound_addresses="$(run_talosctl get addresses 2>/dev/null)" || return 1
    for address in "${pool[@]}"; do
        grep -qF "$address/32" <<<"$bound_addresses" || return 1
    done
    # etcd only answers after the first bootstrap, so this tells a finished
    # control plane from a node that only stored the machine config.
    run_talosctl etcd status >/dev/null 2>&1
}

# The first-boot configuration, rendered to a temporary file whose path is
# printed. Creating a server and reinitialising one need the same document, so
# the rendering lives in one place and neither path can drift from the other.
render_machine_config() {
    local path
    path="$(mktemp)"
    # upgrade-k8s rewrites the component images in the node's live config, and
    # applying a base generated before that move would roll the control plane
    # back, so the base is regenerated at the versions this guide pins.
    # todo: the flags mirror 03-keys.sh; share one call if they diverge.
    talosctl gen config "$RELAY_HOSTNAME" "https://$RELAY_HOSTNAME:6443" \
        --with-secrets "$TALOS_DIR/secrets.yaml" --talos-version "$TALOS_VERSION" \
        --kubernetes-version "$KUBERNETES_VERSION" \
        --install-image "$TALOS_INSTALLER" \
        --output-types controlplane -o "$TALOS_DIR/controlplane.yaml" --force \
        --with-docs=false --with-examples=false >/dev/null
    # The link takes the pool as a YAML flow sequence, which fits on the one
    # template line that envsubst splices it into.
    LINK_ADDRESSES="$(printf '{address: %s/32}, ' "${smtp_addresses[@]}")"
    LINK_ADDRESSES="${LINK_ADDRESSES%, }"
    export LINK_ADDRESSES
    # shellcheck disable=SC2016 # envsubst needs the placeholders unexpanded
    envsubst '${LINK_ADDRESSES}' \
        <"$DEPLOY_DIR/talos/machine-config.patch.yaml.tmpl" >"${path}.patch"
    talosctl machineconfig patch "$TALOS_DIR/controlplane.yaml" \
        --patch "@${path}.patch" -o "$path"
    # The generator writes an UnattendedInstallConfig whenever --install-image
    # is set, and a node booted from the snapshot's installed system runs it on
    # every boot, which is what kept the first --reinit from ever finishing.
    # talosctl validate accepts the document, so the render is checked instead.
    ! grep -q '^kind: UnattendedInstallConfig$' "$path" ||
    fail "the rendered machine config carries UnattendedInstallConfig, which would reinstall the node on every boot and never keep its control plane up. Keep the delete document in deploy/talos/machine-config.patch.yaml.tmpl"
    printf '%s' "$path"
}

# etcd is bootstrapped once, by hand. A request that arrives before the install
# finishes is refused and changes nothing; a node that already bootstrapped
# refuses a second one, which is the state being waited for. The last error is
# kept, so the timeout can name it instead of the loop's discarded output.
bootstrap_etcd() {
    local error
    if error="$("${TALOSCTL[@]}" --nodes "$SERVER_ADDRESS" --endpoints "$SERVER_ADDRESS" bootstrap 2>&1)"; then
        return 0
    fi
    case "$error" in
        *"data directory is not empty"*) return 0 ;;
    esac
    BOOTSTRAP_ERROR="$error"
    return 1
}

# The kubeconfig the workloads, the workflows and kubectl share. Talos hands it
# out of the node's own PKI, so it exists before the API answers.
write_kubeconfig() {
    "${TALOSCTL[@]}" kubeconfig --force --merge=false "$TALOS_DIR/kubeconfig" >/dev/null 2>&1
}

# The API answers, the node is Ready and the API server, controller manager and
# scheduler run as static pods. talosctl health checks the same things, but it
# tracks the node by an address and the egress pool puts two /32 addresses on
# that interface, so it never matches the static pods to the node and spends its
# whole timeout on a healthy cluster.
control_plane_is_ready() {
    local kubeconfig="$TALOS_DIR/kubeconfig"
    kubectl --kubeconfig "$kubeconfig" --request-timeout 10s get --raw=/readyz >/dev/null 2>&1 || return 1
    kubectl --kubeconfig "$kubeconfig" --request-timeout 10s get nodes --no-headers 2>/dev/null |
    awk '$2 != "Ready" { bad = 1 } END { exit (NR < 1 || bad) }' || return 1
    kubectl --kubeconfig "$kubeconfig" --request-timeout 10s get pods --namespace kube-system \
        --no-headers 2>/dev/null |
    awk '
            $1 ~ /^kube-(apiserver|controller-manager|scheduler)-/ {
                found++
                if ($2 != "1/1" || $3 != "Running") bad = 1
            }
            END { exit (found < 3 || bad) }
        '
}

REINIT=false
[ "${1:-}" = "--reinit" ] && REINIT=true

if [ "${1:-}" = "--check" ]; then
    server_is_ready
    exit "$?"
fi

require_hcloud
require_command talosctl envsubst kubectl

if [ "$REINIT" = false ] && server_is_ready; then
    confirm_step server "server $RELAY_HOSTNAME runs Talos with the egress pool assigned"
fi

# A partial pool has to stop here. The machine config would otherwise bind an
# address that was never created, and the sender would only fail on it much
# later, in a receiver's log.
read -ra smtp_addresses <<<"$(fetch_smtp_floating_ip_addresses)"
[ "${#smtp_addresses[@]}" -eq "$SMTP_FLOATING_IP_COUNT" ] ||
fail "the pool holds ${#smtp_addresses[@]} of $SMTP_FLOATING_IP_COUNT addresses. Run ./deploy/provision.sh egress first"

# The keys step generates the machine config and the talosconfig that this step
# patches, hands to the server and talks to the node with.
[ -f "$TALOS_DIR/controlplane.yaml" ] ||
fail "no machine config at $TALOS_DIR/controlplane.yaml. Run ./deploy/provision.sh keys first"
[ -f "$TALOS_DIR/talosconfig" ] ||
fail "no talosconfig at $TALOS_DIR/talosconfig. Run ./deploy/provision.sh keys first"

IMAGE_ID="$(talos_image_id)"
[ -n "$IMAGE_ID" ] ||
fail "no snapshot $TALOS_IMAGE_NAME. Run ./deploy/provision.sh image first"

MACHINE_CONFIG="$(render_machine_config)"
# The rendered template sits next to the printed config, so the trap can name
# both.
MACHINE_CONFIG_PATCH="${MACHINE_CONFIG}.patch"
trap 'rm -f "$MACHINE_CONFIG" "$MACHINE_CONFIG_PATCH"' EXIT

# A node only reports a broken machine config through a boot that never
# finishes, so the same validation the Talos documentation runs before a create
# runs here, where the failure is one line instead of a timeout.
talosctl validate --config "$MACHINE_CONFIG" --mode cloud

# A create and a rebuild deliver the config as user_data; only a kept server
# needs the push below, which binds an address a rerun added to the pool.
APPLY_MACHINE_CONFIG=false

# A server that already exists keeps what it has, whatever booted it. Saying so
# here avoids the confusion of a timeout further down.
# --reinit reinstalls that server instead. Rebuilding keeps the server, so every
# address it holds survives: the primary IP, the floating IPs, and the records
# and PTRs that point at them. The disk does not survive.
if [ "$REINIT" = true ]; then
    server_exists ||
    fail "no server $RELAY_HOSTNAME to reinitialise. Run ./deploy/provision.sh server first"
    note "Reinstalling $RELAY_HOSTNAME from $TALOS_IMAGE_NAME, keeping its addresses"
    note "The disk is erased. Anything running on it stops until the deploy workflow runs again."
    hcloud server rebuild \
        --image "$IMAGE_ID" \
        --user-data-from-file "$MACHINE_CONFIG" \
        "$RELAY_HOSTNAME" >/dev/null
elif server_exists; then
    image_id="$(fetch_server_image_id)"
    if [ -n "$image_id" ] && [ "$image_id" != "$IMAGE_ID" ]; then
        fail "server $RELAY_HOSTNAME was built from image $image_id, not $TALOS_IMAGE_NAME, so it has never run this guide's first boot. Run ./deploy/steps/05-server.sh --reinit to reinstall it in place, which keeps its addresses."
    fi
    note "Server $RELAY_HOSTNAME already exists, keeping it as-is (not re-initialised)"
    APPLY_MACHINE_CONFIG=true
else
    # Only a create needs the type and location. A rebuild keeps the server it
    # already has, so validating the configured pair would block it for nothing.
    validate_server_type_location
    note "Creating $SERVER_TYPE server $RELAY_HOSTNAME in $SERVER_LOCATION"
    hcloud server create \
        --name "$RELAY_HOSTNAME" \
        --type "$SERVER_TYPE" \
        --image "$IMAGE_ID" \
        --location "$SERVER_LOCATION" \
        --label relay=server \
        --user-data-from-file "$MACHINE_CONFIG" >/dev/null
fi

SERVER_ID="$(fetch_server_id)"
SERVER_ADDRESS="$(fetch_server_address)"
[ -n "$SERVER_ID" ] || fail "hcloud reports no server $RELAY_HOSTNAME"
[ -n "$SERVER_ADDRESS" ] || fail "hcloud reports no address for server $RELAY_HOSTNAME"

for ((index = 1; index <= SMTP_FLOATING_IP_COUNT; index++)); do
    name="$(smtp_floating_ip_name "$index")"
    if [ "$(floating_ip_server_id "$name")" = "$SERVER_ID" ]; then
        note "Floating IP $name is already assigned"
    else
        note "Assigning floating IP $name"
        hcloud floating-ip assign "$name" "$RELAY_HOSTNAME" >/dev/null
    fi
done

SMTP_FLOATING_IP_ADDRESSES="$(comma_list "${smtp_addresses[@]}")"
SMTP_SOURCE_ADDRESSES="$SMTP_FLOATING_IP_ADDRESSES,$SERVER_ADDRESS"
save_state "SERVER_ID=$SERVER_ID" "SERVER_ADDRESS=$SERVER_ADDRESS" \
    "SMTP_FLOATING_IP_ADDRESSES=$SMTP_FLOATING_IP_ADDRESSES" \
    "SMTP_SOURCE_ADDRESSES=$SMTP_SOURCE_ADDRESSES"

# Everything below talks to the node, not to hcloud. The address goes into the
# talosconfig because the records that resolve $RELAY_HOSTNAME are created only
# after this step; the kubeconfig the node generates points at the cluster
# endpoint either way.
"${TALOSCTL[@]}" config endpoint "$SERVER_ADDRESS" >/dev/null
"${TALOSCTL[@]}" config node "$SERVER_ADDRESS" >/dev/null

wait_until "the machine config on $SERVER_ADDRESS" talos_is_configured

if [ "$APPLY_MACHINE_CONFIG" = true ]; then
    note "Applying the machine config to the running node"
    "${TALOSCTL[@]}" apply-config --nodes "$SERVER_ADDRESS" --endpoints "$SERVER_ADDRESS" \
        --file "$MACHINE_CONFIG" >/dev/null
fi

wait_until "the etcd bootstrap" bootstrap_etcd ||
fail "the etcd bootstrap did not complete: ${BOOTSTRAP_ERROR:-talosctl bootstrap reported no output}"

note "Writing $TALOS_DIR/kubeconfig"
wait_until "the kubeconfig" write_kubeconfig ||
fail "talosctl kubeconfig did not hand one out. Read the node: talosctl --talosconfig $TALOS_DIR/talosconfig dmesg"

wait_until "the control plane" control_plane_is_ready ||
fail "the control plane did not come up. Read the API server: kubectl --kubeconfig $TALOS_DIR/kubeconfig logs --namespace kube-system -l component=kube-apiserver"

record_step server "created $SERVER_TYPE server $SERVER_ID in $SERVER_LOCATION as $SERVER_ADDRESS"

note "Server address: $SERVER_ADDRESS"
note "Egress addresses: $SMTP_SOURCE_ADDRESSES"
