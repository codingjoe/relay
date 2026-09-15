#!/usr/bin/env bash
#
# Provisioning step: wait until the registrar delegates the zone to the
# Hetzner nameservers.
#
# The registrar is the one thing no script can change, so this step prints the
# delegation, watches it, and stops when it does not appear in time. Run it
# again after you changed the delegation at your registrar.
#
# Inputs: RELAY_HOSTNAME, PUBLIC_RESOLVERS, WAIT_TIMEOUT_SECS, WAIT_INTERVAL_SECS

set -euo pipefail

STEPS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../config.sh
source "$(dirname "$STEPS_DIR")/config.sh"
# shellcheck source=../hcloud.sh
source "$DEPLOY_DIR/hcloud.sh"
# shellcheck source=../dns.sh
source "$DEPLOY_DIR/dns.sh"

nameservers=()
NAMESERVERS="$(fetch_zone_nameservers)"
read -ra nameservers <<<"$NAMESERVERS"

# The resolvers are the authority here, not the zone's own status: they answer
# what the parent zone delegates to, which is what the rest of the world sees.
delegation_is_live() {
    local resolver
    [ -n "$NAMESERVERS" ] || return 1
    for resolver in "${PUBLIC_RESOLVERS[@]}"; do
        dns_has_records NS "$RELAY_HOSTNAME" "$resolver" "${nameservers[@]}" || return 1
    done
}

if [ "${1:-}" = "--check" ]; then
    delegation_is_live
    exit "$?"
fi

require_hcloud
require_command dig

if [ -z "$NAMESERVERS" ]; then
    fail "zone $RELAY_HOSTNAME does not exist. Run ./deploy/provision.sh zone first"
fi

if delegation_is_live; then
    if [ "$(fetch_zone_delegation_status)" != "valid" ]; then
        warn "the resolvers agree, but Hetzner reports the delegation as $(fetch_zone_delegation_status)"
    fi
    confirm_step delegation "$RELAY_HOSTNAME is delegated to $NAMESERVERS"
fi

cat <<EOF

Point $RELAY_HOSTNAME at these nameservers in your registrar:

$(printf '  %s\n' "${nameservers[@]}")

Hetzner currently reports the delegation as $(fetch_zone_delegation_status).
EOF

if ! wait_until "the delegation of $RELAY_HOSTNAME" "$WAIT_TIMEOUT_SECS" "$WAIT_INTERVAL_SECS" delegation_is_live; then
    cat <<EOF

The registrars are not there yet. Nothing else can be verified before they
are, so set the nameservers above and run this again:

  ./deploy/provision.sh delegation
EOF
    exit "$EXIT_INCOMPLETE"
fi

save_state "ZONE_NAMESERVERS=$NAMESERVERS"
record_step delegation "delegated to $NAMESERVERS"
