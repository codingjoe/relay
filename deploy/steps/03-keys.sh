#!/usr/bin/env bash
#
# Provisioning step: create the deployment SSH key pair and upload the SSH
# keys to Hetzner Cloud.
#
# Inputs: RELAY_HOSTNAME, SSH_PUBLIC_KEY_FILES, DEPLOY_KEY

set -euo pipefail

STEPS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../config.sh
source "$(dirname "$STEPS_DIR")/config.sh"
# shellcheck source=../hcloud.sh
source "$DEPLOY_DIR/hcloud.sh"

# Hetzner cannot change the material of an uploaded key, so compare it. A
# regenerated pair would otherwise leave the server with a key nobody holds.
ssh_keys_are_uploaded() {
    local key_name key_file
    [ -f "${DEPLOY_KEY}.pub" ] || return 1
    while IFS=$'\t' read -r key_name key_file; do
        [ "$(uploaded_ssh_key "$key_name")" = "$(cat "$key_file")" ] || return 1
    done < <(ssh_key_pairs)
}

if [ "${1:-}" = "--check" ]; then
    ssh_keys_are_uploaded
    exit "$?"
fi

require_hcloud
require_command ssh-keygen

if ssh_keys_are_uploaded; then
    confirm_step keys "${DEPLOY_KEY}.pub is uploaded as $DEPLOY_KEY_NAME"
fi

if [ -f "${DEPLOY_KEY}.pub" ]; then
    note "Reusing ${DEPLOY_KEY}.pub"
elif [ -f "$DEPLOY_KEY" ]; then
    note "Deriving ${DEPLOY_KEY}.pub from $DEPLOY_KEY"
    ssh-keygen -y -f "$DEPLOY_KEY" >"${DEPLOY_KEY}.pub"
else
    note "Creating $DEPLOY_KEY"
    ssh-keygen -t ed25519 -N "" -C "deploy@${RELAY_HOSTNAME}" -f "$DEPLOY_KEY" >/dev/null
fi

while IFS=$'\t' read -r key_name key_file; do
    if [ ! -f "$key_file" ]; then
        warn "SSH public key not found, skipping: $key_file"
        continue
    fi
    uploaded="$(uploaded_ssh_key "$key_name")"
    if [ -z "$uploaded" ]; then
        note "Uploading SSH key $key_name"
        hcloud ssh-key create --name "$key_name" --public-key-from-file "$key_file" --label relay=deploy >/dev/null
    elif [ "$uploaded" != "$(cat "$key_file")" ]; then
        fail "$key_name holds another public key than $key_file. Delete the uploaded key, then run this step again: hcloud ssh-key delete $key_name"
    else
        note "SSH key $key_name is up to date"
    fi
done < <(ssh_key_pairs)

record_step keys "deploy key $DEPLOY_KEY, uploaded $(ssh_key_names | tr '\n' ' ')"
