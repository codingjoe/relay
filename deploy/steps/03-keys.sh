#!/usr/bin/env bash
#
# Provisioning step: create the Talos cluster secrets and the client configs
# that reach the cluster.
#
# Inputs: RELAY_HOSTNAME, TALOS_DIR, TALOS_VERSION

set -euo pipefail

STEPS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../config.sh
source "$(dirname "$STEPS_DIR")/config.sh"

SECRETS_FILE="$TALOS_DIR/secrets.yaml"
CONTROLPLANE_FILE="$TALOS_DIR/controlplane.yaml"
TALOSCONFIG_FILE="$TALOS_DIR/talosconfig"
READER_TALOSCONFIG_FILE="$TALOS_DIR/talosconfig-reader"
CLUSTER_ENDPOINT="https://$RELAY_HOSTNAME:6443"

# The bundle signs every client certificate and holds the etcd encryption key,
# so it is the cluster's recovery input: create it once and keep it.
talos_configs_are_issued() {
    [ -f "$SECRETS_FILE" ] && [ -f "$CONTROLPLANE_FILE" ] &&
    [ -f "$TALOSCONFIG_FILE" ] && [ -f "$READER_TALOSCONFIG_FILE" ]
}

if [ "${1:-}" = "--check" ]; then
    talos_configs_are_issued
    exit "$?"
fi

require_command talosctl

# The bundle signs every client certificate and holds the etcd encryption key,
# and the generated configs carry the cluster CA and the service-account key.
# The ssh-keygen pair this step replaced was 0600, so nothing here may be
# readable by another local account, on the first run or on a rerun.
umask 077
mkdir -p "$TALOS_DIR"
chmod 700 "$TALOS_DIR"
for file in "$SECRETS_FILE" "$CONTROLPLANE_FILE" "$TALOSCONFIG_FILE" \
    "$READER_TALOSCONFIG_FILE"; do
    [ -f "$file" ] || continue
    chmod 600 "$file"
done

if [ -f "$TALOSCONFIG_FILE" ]; then
    # Talos does not rotate client certificates: they stop working one year
    # after they were issued, and only the secrets bundle brings them back.
    note "Client certificates last one year and are not rotated:"
    for file in "$TALOSCONFIG_FILE" "$READER_TALOSCONFIG_FILE"; do
        [ -f "$file" ] || continue
        note "$file"
        talosctl --talosconfig "$file" config info | sed 's/^/        /'
    done
fi

if talos_configs_are_issued; then
    confirm_step keys "the cluster secrets and client configs are in $TALOS_DIR"
fi

# A generated config without the bundle that signed it cannot be tied back to
# it, so refuse to mint an unrelated bundle next to it.
if [ ! -f "$SECRETS_FILE" ] &&
{ [ -f "$CONTROLPLANE_FILE" ] || [ -f "$TALOSCONFIG_FILE" ] || [ -f "$READER_TALOSCONFIG_FILE" ]; }; then
    fail "$TALOS_DIR holds generated configs but no $SECRETS_FILE. Restore the bundle that signed them, or delete $TALOS_DIR and run this step again to start over."
fi

if [ -f "$SECRETS_FILE" ]; then
    note "Reusing $SECRETS_FILE"
else
    note "Creating $SECRETS_FILE"
    talosctl gen secrets --talos-version "$TALOS_VERSION" -o "$SECRETS_FILE"
fi

if [ ! -f "$CONTROLPLANE_FILE" ]; then
    note "Generating $CONTROLPLANE_FILE"
    # The image the node installs to disk has to be the hcloud build of the
    # same schematic as the snapshot: the generator names the metal installer,
    # and a node installed from that build comes up without the Hetzner
    # platform support or the guest agent.
    talosctl gen config "$RELAY_HOSTNAME" "$CLUSTER_ENDPOINT" \
        --with-secrets "$SECRETS_FILE" --talos-version "$TALOS_VERSION" \
        --install-image "$TALOS_INSTALLER" \
        --output-types controlplane -o "$CONTROLPLANE_FILE" \
        --with-docs=false --with-examples=false
fi

if [ ! -f "$TALOSCONFIG_FILE" ]; then
    note "Generating $TALOSCONFIG_FILE"
    talosctl gen config "$RELAY_HOSTNAME" "$CLUSTER_ENDPOINT" \
        --with-secrets "$SECRETS_FILE" --talos-version "$TALOS_VERSION" \
        --output-types talosconfig -o "$TALOSCONFIG_FILE"
    # gen config leaves the context without an endpoint, so nothing reaches
    # the cluster until they are set.
    talosctl --talosconfig "$TALOSCONFIG_FILE" config endpoint "$RELAY_HOSTNAME"
    talosctl --talosconfig "$TALOSCONFIG_FILE" config node "$RELAY_HOSTNAME"
fi

# The node signs the reader certificate, so it can only be issued once the node
# answers: the first run leaves it, and a rerun of this step after the server
# exists issues it.
if [ ! -f "$READER_TALOSCONFIG_FILE" ]; then
    if talosctl --talosconfig "$TALOSCONFIG_FILE" version --short >/dev/null 2>&1; then
        note "Issuing $READER_TALOSCONFIG_FILE for os:reader"
        talosctl --talosconfig "$TALOSCONFIG_FILE" config new "$READER_TALOSCONFIG_FILE" --roles os:reader
        talosctl --talosconfig "$READER_TALOSCONFIG_FILE" config node "$RELAY_HOSTNAME"
    else
        note "The Talos API does not answer yet, so $READER_TALOSCONFIG_FILE is not issued."
        note "Run ./deploy/provision.sh keys again once ./deploy/provision.sh server has created the cluster."
    fi
fi

note "Keep $SECRETS_FILE: it reissues every client certificate and is the cluster recovery input."
record_step keys "secrets bundle and client configs in $TALOS_DIR"
