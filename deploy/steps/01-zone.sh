#!/usr/bin/env bash
#
# Provisioning step: create the Hetzner Cloud DNS zone.
#
# The zone comes first. It is the one resource the operator has to hand to a
# third party, and every step after it is verified by looking the zone up.
#
# Inputs: RELAY_HOSTNAME

set -euo pipefail

STEPS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../config.sh
source "$(dirname "$STEPS_DIR")/config.sh"
# shellcheck source=../hcloud.sh
source "$DEPLOY_DIR/hcloud.sh"

if [ "${1:-}" = "--check" ]; then
    zone_exists
    exit "$?"
fi

require_hcloud

if zone_exists; then
    confirm_step zone "the zone $RELAY_HOSTNAME exists"
fi


note "Creating zone $RELAY_HOSTNAME"
hcloud zone create --name "$RELAY_HOSTNAME" --label relay=zone >/dev/null

ZONE_NAMESERVERS="$(fetch_zone_nameservers)"
[ -n "$ZONE_NAMESERVERS" ] || fail "created zone $RELAY_HOSTNAME but hcloud reports no nameservers for it"
save_state "ZONE_NAMESERVERS=$ZONE_NAMESERVERS"
record_step zone "created zone $RELAY_HOSTNAME with nameservers $ZONE_NAMESERVERS"

note "Nameservers: $ZONE_NAMESERVERS"
note "The delegation step hands these to your registrar."
