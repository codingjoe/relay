#!/usr/bin/env bash
#
# Provisioning step: create the server and assign the egress pool to it.
#
# The server boots with cloud-init, which creates the deploy users and binds
# the floating IPs to eth0, so the pool has to exist first.
#
# Inputs: RELAY_HOSTNAME, SERVER_TYPE, SERVER_LOCATION,
#         SMTP_FLOATING_IP_COUNT, DEPLOY_KEY, SSH_PUBLIC_KEY_FILES

set -euo pipefail

STEPS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../config.sh
source "$(dirname "$STEPS_DIR")/config.sh"
# shellcheck source=../hcloud.sh
source "$DEPLOY_DIR/hcloud.sh"

# A server that exists is not enough: it has to be the one this guide built, and
# the egress pool has to be assigned to it, or the sender cannot bind the
# addresses it sends from. The image is what tells a box that ran this step's
# first boot from one that predates it, because a Docker host has the same name,
# the same address and the same pool, and would otherwise be reported as done
# while it has no k3s at all. An unreadable image name is not a mismatch, so a
# box built from an image Hetzner has since deprecated is not condemned by it.
server_image_is_expected() {
    local image
    image="$(fetch_server_image_name)"
    [ -z "$image" ] || [ "$image" = "$SERVER_IMAGE" ]
}

server_is_ready() {
    local index server_id
    server_id="$(fetch_server_id)"
    [ -n "$server_id" ] || return 1
    [ "$(fetch_server_status)" = "running" ] || return 1
    server_image_is_expected || return 1
    for ((index = 1; index <= SMTP_FLOATING_IP_COUNT; index++)); do
        [ "$(floating_ip_server_id "$(smtp_floating_ip_name "$index")")" = "$server_id" ] || return 1
    done
}

# The first-boot configuration, rendered to a temporary file whose path is
# printed. Creating a server and reinitialising one need the same file, so the
# rendering lives in one place and neither path can drift from the other.
render_cloud_init() {
    local path
    path="$(mktemp)"
    DEPLOY_PUBLIC_KEY="$(cat "${DEPLOY_KEY}.pub")"
    # netplan takes the pool as a YAML flow sequence, which fits on the one
    # template line that envsubst splices it into.
    NETPLAN_ADDRESSES="$(comma_list "${smtp_addresses[@]/%//32}")"
    export DEPLOY_PUBLIC_KEY NETPLAN_ADDRESSES K3S_INSTALL_FLAGS RELAY_NAMESPACE
    envsubst "\${DEPLOY_PUBLIC_KEY} \${NETPLAN_ADDRESSES} \${K3S_INSTALL_FLAGS} \${RELAY_NAMESPACE}" \
        <"$DEPLOY_DIR/cloud-init.yaml.tmpl" >"$path"
    printf '%s' "$path"
}

REINIT=false
[ "${1:-}" = "--reinit" ] && REINIT=true

if [ "${1:-}" = "--check" ]; then
    server_is_ready
    exit "$?"
fi

require_hcloud
require_command envsubst

if [ "$REINIT" = false ] && server_is_ready; then
    confirm_step server "server $RELAY_HOSTNAME runs with the egress pool assigned"
fi

[ -f "${DEPLOY_KEY}.pub" ] ||
fail "no deploy key at ${DEPLOY_KEY}.pub. Run ./deploy/provision.sh keys first"

# A partial pool has to stop here. The assignment loop below would otherwise
# ask hcloud to assign an address that was never created and fail with an
# opaque error instead of the step that actually needs running.
read -ra smtp_addresses <<<"$(fetch_smtp_floating_ip_addresses)"
[ "${#smtp_addresses[@]}" -eq "$SMTP_FLOATING_IP_COUNT" ] ||
fail "the pool holds ${#smtp_addresses[@]} of $SMTP_FLOATING_IP_COUNT addresses. Run ./deploy/provision.sh egress first"

# user_data applies at first boot only, so a server that already exists was
# built by something else and keeps what it has, k3s included. Saying so here
# avoids the confusion of a later timeout at the environment step.
# --reinit reinstalls that server instead. Rebuilding keeps the server, so every
# address it holds survives: the primary IP, the floating IPs, and the records
# and PTRs that point at them. The disk does not survive.
if [ "$REINIT" = true ]; then
    server_exists ||
    fail "no server $RELAY_HOSTNAME to reinitialise. Run ./deploy/provision.sh server first"
    CLOUD_INIT="$(render_cloud_init)"
    trap 'rm -f "$CLOUD_INIT"' EXIT
    note "Reinstalling $RELAY_HOSTNAME as $SERVER_IMAGE, keeping its addresses"
    note "The disk is erased. Anything running on it stops until the deploy workflow runs again."
    hcloud server rebuild \
        --image "$SERVER_IMAGE" \
        --user-data-from-file "$CLOUD_INIT" \
        "$RELAY_HOSTNAME" >/dev/null
elif server_exists; then
    image="$(fetch_server_image_name)"
    if [ -n "$image" ] && [ "$image" != "$SERVER_IMAGE" ]; then
        fail "server $RELAY_HOSTNAME was built from \"$image\", not $SERVER_IMAGE, so it has never run this guide's first boot and has no k3s. Run ./deploy/steps/05-server.sh --reinit to reinstall it in place, which keeps its addresses."
    fi
    note "Server $RELAY_HOSTNAME already exists, keeping it as-is (not re-initialised)"
else
    # Only a create needs the type and location. A rebuild keeps the server it
    # already has, so validating the configured pair would block it for nothing.
    validate_server_type_location
    CLOUD_INIT="$(render_cloud_init)"
    trap 'rm -f "$CLOUD_INIT"' EXIT

    note "Creating $SERVER_TYPE server $RELAY_HOSTNAME in $SERVER_LOCATION"
    server_arguments=(
        --name "$RELAY_HOSTNAME"
        --type "$SERVER_TYPE"
        --image "$SERVER_IMAGE"
        --location "$SERVER_LOCATION"
        --label relay=server
        --user-data-from-file "$CLOUD_INIT"
    )
    while read -r key_name; do
        server_arguments+=(--ssh-key "$key_name")
    done < <(ssh_key_names)
    hcloud server create "${server_arguments[@]}" >/dev/null
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
record_step server "created $SERVER_TYPE server $SERVER_ID in $SERVER_LOCATION as $SERVER_ADDRESS"

note "Server address: $SERVER_ADDRESS"
note "Egress addresses: $SMTP_SOURCE_ADDRESSES"
