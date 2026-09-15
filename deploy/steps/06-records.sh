#!/usr/bin/env bash
#
# Provisioning step: publish the records and the PTR records of this
# deployment.
#
# Each egress address needs a forward record for its PTR, and receivers
# confirm them by looking the name up forward, so the records are what make the
# pool verifiable.
#
# Inputs: RELAY_HOSTNAME, SMTP_FLOATING_IP_COUNT

set -euo pipefail

STEPS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../config.sh
source "$(dirname "$STEPS_DIR")/config.sh"
# shellcheck source=../hcloud.sh
source "$DEPLOY_DIR/hcloud.sh"
# shellcheck source=../dns.sh
source "$DEPLOY_DIR/dns.sh"

# Ask the zone itself, so a record Hetzner accepted is visible right away
# instead of waiting for the delegation and the resolvers.
records_are_published() {
    local nameserver
    nameserver="$(first_zone_nameserver)"
    [ -n "$nameserver" ] || return 1
    a_records_resolve "$nameserver" || return 1
    ptr_records_are_set
}

if [ "${1:-}" = "--check" ]; then
    records_are_published
    exit "$?"
fi

require_hcloud
require_command dig

if records_are_published; then
    confirm_step records "the zone and the PTR records answer for this deployment"
fi

SERVER_ADDRESS="$(fetch_server_address)"
[ -n "$SERVER_ADDRESS" ] ||
fail "no server named $RELAY_HOSTNAME. Run ./deploy/provision.sh server first"

read -ra nameservers <<<"$(fetch_zone_nameservers)"
[ -n "${nameservers[0]:-}" ] ||
fail "zone $RELAY_HOSTNAME does not exist. Run ./deploy/provision.sh zone first"

read -ra smtp_addresses <<<"$(fetch_smtp_floating_ip_addresses)"
[ -n "${smtp_addresses[0]:-}" ] ||
fail "no SMTP floating IPs found. Run ./deploy/provision.sh egress first"

while read -r record_name; do
    hcloud zone rrset set-records --record "$SERVER_ADDRESS" "$RELAY_HOSTNAME" "$record_name" A >/dev/null
done < <(zone_record_names)

for ((index = 0; index < ${#smtp_addresses[@]}; index++)); do
    position=$((index + 1))
    address="${smtp_addresses[$index]}"
    hcloud zone rrset set-records --record "$address" "$RELAY_HOSTNAME" "sender-${position}.mail" A >/dev/null
    hcloud floating-ip set-rdns \
        --ip "$address" \
        --hostname "$(sender_hostname "$position")" \
        "$(smtp_floating_ip_name "$position")" >/dev/null
done

hcloud server set-rdns --ip "$SERVER_ADDRESS" --hostname "$RELAY_HOSTNAME" "$RELAY_HOSTNAME" >/dev/null

SMTP_FLOATING_IP_ADDRESSES="$(comma_list "${smtp_addresses[@]}")"
save_state "SMTP_FLOATING_IP_ADDRESSES=$SMTP_FLOATING_IP_ADDRESSES" \
    "SMTP_SOURCE_ADDRESSES=$SMTP_FLOATING_IP_ADDRESSES,$SERVER_ADDRESS"
record_step records "published A and PTR records for $SERVER_ADDRESS and $SMTP_FLOATING_IP_ADDRESSES"

note "A records point at $SERVER_ADDRESS"
note "PTRs: $SERVER_ADDRESS and $SMTP_FLOATING_IP_ADDRESSES answer as sender names"
