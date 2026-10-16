#!/usr/bin/env bash
#
# Provisioning step: upload the Talos hcloud disk image as a snapshot.
#
# Hetzner cannot boot a disk image from a URL. hcloud-upload-image boots a
# temporary server in SERVER_LOCATION, writes the image to its disk, snapshots
# that disk and deletes the server, and the snapshot is what the server step
# boots.
#
# Inputs: SERVER_LOCATION, TALOS_VERSION, TALOS_SCHEMATIC, TALOS_IMAGE_NAME

set -euo pipefail

STEPS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../config.sh
source "$(dirname "$STEPS_DIR")/config.sh"
# shellcheck source=../hcloud.sh
source "$DEPLOY_DIR/hcloud.sh"

if [ "${1:-}" = "--check" ]; then
    talos_image_exists
    exit "$?"
fi

require_hcloud
require_command hcloud-upload-image
# hcloud-upload-image reads the API token from the environment; the context the
# hcloud CLI keeps is not enough for it.
require_env HCLOUD_TOKEN

if talos_image_exists; then
    confirm_step image "snapshot $TALOS_IMAGE_NAME exists"
fi

# The URL is the schematic's build for the architecture hcloud runs, and it is
# the same build the machine config hands the node to install.
TALOS_IMAGE_URL="https://factory.talos.dev/image/${TALOS_SCHEMATIC}/${TALOS_VERSION}/hcloud-amd64.raw.xz"

note "Uploading $TALOS_IMAGE_NAME in $SERVER_LOCATION"
note "This boots a temporary server, writes the image to its disk and snapshots it"
hcloud-upload-image upload \
    --image-url "$TALOS_IMAGE_URL" \
    --architecture x86 \
    --compression xz \
    --location "$SERVER_LOCATION" \
    --description "$TALOS_IMAGE_NAME" \
    --labels relay=image

talos_image_exists ||
fail "hcloud reports no snapshot $TALOS_IMAGE_NAME after the upload"

record_step image "uploaded snapshot $TALOS_IMAGE_NAME from $TALOS_IMAGE_URL"
