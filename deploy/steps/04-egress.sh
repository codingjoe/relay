#!/usr/bin/env bash
#
# Provisioning step: create the pool of floating IPs that carries outbound
# mail.
#
# Each address gets its own PTR record later, so receivers can confirm it. The
# server binds them at first boot, so this step comes before the server.
#
# Inputs: RELAY_HOSTNAME, SERVER_LOCATION, SMTP_FLOATING_IP_COUNT

set -euo pipefail

STEPS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../config.sh
source "$(dirname "$STEPS_DIR")/config.sh"
# shellcheck source=../hcloud.sh
source "$DEPLOY_DIR/hcloud.sh"

egress_addresses_exist() {
    local index
    for ((index = 1; index <= SMTP_FLOATING_IP_COUNT; index++)); do
        floating_ip_exists "$(smtp_floating_ip_name "$index")" || return 1
    done
}

if [ "${1:-}" = "--check" ]; then
    egress_addresses_exist
    exit "$?"
fi

require_hcloud

if egress_addresses_exist; then
    confirm_step egress "the pool of $SMTP_FLOATING_IP_COUNT floating IPs exists"
fi


for ((index = 1; index <= SMTP_FLOATING_IP_COUNT; index++)); do
    name="$(smtp_floating_ip_name "$index")"
    if floating_ip_exists "$name"; then
        note "Floating IP $name already exists"
    else
        note "Creating floating IP $name in $SERVER_LOCATION"
        hcloud floating-ip create \
            --name "$name" \
            --type ipv4 \
            --home-location "$SERVER_LOCATION" \
            --label relay=smtp \
            --description "SMTP egress IP ${index} for ${RELAY_HOSTNAME}" >/dev/null
    fi
done

read -ra smtp_addresses <<<"$(fetch_smtp_floating_ip_addresses)"
[ -n "${smtp_addresses[0]:-}" ] ||
fail "created the floating IPs but hcloud reports no address for them"

note "Egress pool: $(fetch_smtp_floating_ip_addresses)"
save_state "SMTP_FLOATING_IP_ADDRESSES=$(fetch_smtp_floating_ip_addresses)"
record_step egress "created ${#smtp_addresses[@]} egress addresses: $(fetch_smtp_floating_ip_addresses)"
