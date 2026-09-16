#!/usr/bin/env bash
#
# Provisioning step: create the Hetzner Object Storage bucket that holds
# stored mail.
#
# Inputs: S3_BUCKET, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY

set -euo pipefail

STEPS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../config.sh
source "$(dirname "$STEPS_DIR")/config.sh"

bucket_exists() {
    aws --endpoint-url "$S3_ENDPOINT_URL" s3api head-bucket --bucket "$S3_BUCKET" >/dev/null 2>&1
}

if [ "${1:-}" = "--check" ]; then
    bucket_exists
    exit "$?"
fi

require_command aws
require_env AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY

if bucket_exists; then
    confirm_step storage "bucket $S3_BUCKET exists"
fi

# Only create-bucket. Hetzner Object Storage implements no ACL or ownership
# API, and relay never sets object ACLs: one credential pair writes and reads
# every object, so there is no second owner to reconcile.
note "Creating bucket $S3_BUCKET at $S3_ENDPOINT_URL"
aws --endpoint-url "$S3_ENDPOINT_URL" s3api create-bucket \
    --bucket "$S3_BUCKET" \
    --create-bucket-configuration "LocationConstraint=${S3_REGION}" >/dev/null

save_state "S3_BUCKET=$S3_BUCKET"
record_step storage "created bucket $S3_BUCKET at $S3_ENDPOINT_URL"

note "Objects are private. The storage container serves them through Caddy on signed URLs that expire."
note "The bucket holds stored mail, so emptying it deletes that mail."
