#!/usr/bin/env bash
#
# Provisioning step: wait until public resolvers answer with the records of
# this deployment.
#
# The server side of the zone is done once the records are written, but
# resolvers keep whatever they cached, including the negative answers of a
# name that did not exist yet. This step is what makes a browser, a mail relay
# and the certificate authority agree.
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

# Every resolver has to agree, because a client picks one at random.
records_are_propagated() {
    local resolver
    for resolver in "${PUBLIC_RESOLVERS[@]}"; do
        a_records_resolve "$resolver" || return 1
        ptr_records_are_propagated "$resolver" || return 1
    done
}

if [ "${1:-}" = "--check" ]; then
    records_are_propagated
    exit "$?"
fi

require_hcloud
require_command dig

if records_are_propagated; then
    confirm_step propagation "every resolver answers with the records of $RELAY_HOSTNAME"
fi

note "Waiting for ${PUBLIC_RESOLVERS[*]} to answer with the records of $RELAY_HOSTNAME"
if ! wait_until "the records of $RELAY_HOSTNAME" \
    "$WAIT_TIMEOUT_SECS" "$WAIT_INTERVAL_SECS" records_are_propagated; then
    cat <<EOF

The resolvers still answer with something else:

$(for resolver in "${PUBLIC_RESOLVERS[@]}"; do
        printf '  %-16s %s\n' "$resolver" "$(dns_answers A "$RELAY_HOSTNAME" "$resolver")"
    done)

A cached negative answer can outlive the records by one TTL. Run this again in
a few minutes, or check a resolver yourself:

  dig A $RELAY_HOSTNAME @${PUBLIC_RESOLVERS[0]}
EOF
    exit "$EXIT_INCOMPLETE"
fi

record_step propagation "records visible at ${PUBLIC_RESOLVERS[*]}"
