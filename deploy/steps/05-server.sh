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

# A server that exists is not enough: the egress pool has to be assigned to it
# as well, or the sender cannot bind the addresses it sends from.
server_is_ready() {
    local index server_id
    server_id="$(fetch_server_id)"
    [ -n "$server_id" ] || return 1
    [ "$(fetch_server_status)" = "running" ] || return 1
    for ((index = 1; index <= SMTP_FLOATING_IP_COUNT; index++)); do
        [ "$(floating_ip_server_id "$(smtp_floating_ip_name "$index")")" = "$server_id" ] || return 1
    done
}

if [ "${1:-}" = "--check" ]; then
    server_is_ready
    exit "$?"
fi

require_hcloud
require_command envsubst

if server_is_ready; then
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

validate_server_type_location

if server_exists; then
    note "Server $RELAY_HOSTNAME already exists"
else
    CLOUD_INIT="$(mktemp)"
    trap 'rm -f "$CLOUD_INIT"' EXIT
    DEPLOY_PUBLIC_KEY="$(cat "${DEPLOY_KEY}.pub")"
    # netplan takes the pool as a YAML flow sequence, which fits on the one
    # template line that envsubst splices it into.
    NETPLAN_ADDRESSES="$(comma_list "${smtp_addresses[@]/%//32}")"
    export DEPLOY_PUBLIC_KEY NETPLAN_ADDRESSES
    envsubst "\${DEPLOY_PUBLIC_KEY} \${NETPLAN_ADDRESSES}" \
        <"$DEPLOY_DIR/cloud-init.yaml.tmpl" >"$CLOUD_INIT"

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
