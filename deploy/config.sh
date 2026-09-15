# shellcheck shell=bash
# shellcheck disable=SC2034 # the steps consume most of these
#
# Configuration, recorded state and output helpers for the provisioning steps.
#
# Every script under deploy/ sources this file. It resolves the configuration
# from the environment, loads what earlier steps recorded, and prints the
# progress of a run.
#
# A step never decides from the state file alone. It checks the resource
# itself, so deleting a server or a record makes the step run again. The state
# file only remembers what a run created, so a rerun does not have to ask:
#
#   deploy/.state/state.env    the values the deployment created
#   deploy/.state/steps/<name> when a step last ran and what it did
#
# Inputs, with defaults in parentheses:
#
#   RELAY_HOSTNAME          (relays.to)              public hostname
#   SERVER_TYPE             (ccx33)                  hcloud server type
#   SERVER_IMAGE            (docker-ce)              hcloud image
#   SERVER_LOCATION         (fsn1)                   hcloud location
#   SMTP_FLOATING_IP_COUNT  (2)                      size of the SMTP egress pool
#   S3_ENDPOINT             (fsn1.your-objectstorage.com)
#   S3_REGION               (fsn1)
#   S3_BUCKET               (relay-<hostname with dots replaced by dashes>)
#   RELAY_STORAGE_DOMAIN    (storage.<hostname>)  the name Caddy serves
#                           stored message bodies on, inside the zone
#   SSH_PUBLIC_KEY_FILES    (~/.ssh/id_ed25519.pub)  space separated
#   DEPLOY_KEY              (deploy/id_ed25519)
#   PUBLIC_RESOLVERS        (1.1.1.1 9.9.9.9)        space separated
#   WAIT_TIMEOUT_SECS       (600)
#   WAIT_INTERVAL_SECS      (15)
#
# See deploy/README.md for the full operator guide.

# A step returns these instead of failing: provision.sh reports them and stops.
EXIT_SKIPPED=10
EXIT_INCOMPLETE=11

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$DEPLOY_DIR")"

# gh, dotenvx and the deployment workflow all resolve the repository from the
# working directory.
cd "$REPO_ROOT" || exit 1

STATE_DIR="${RELAY_STATE_DIR:-$DEPLOY_DIR/.state}"
STATE_FILE="$STATE_DIR/state.env"
STEP_RECORD_DIR="$STATE_DIR/steps"

# The values a run records, in the order the state file lists them.
STATE_KEYS=(
    RELAY_HOSTNAME
    SERVER_ID
    SERVER_ADDRESS
    SMTP_FLOATING_IP_ADDRESSES
    SMTP_SOURCE_ADDRESSES
    ZONE_NAMESERVERS
    SSH_KNOWN_HOSTS
    S3_ENDPOINT_URL
    S3_BUCKET
    UPDATED_AT
)

log() {
    printf '\n==> %s\n' "$*"
}

note() {
    printf '    %s\n' "$*"
}

warn() {
    printf 'warning: %s\n' "$*" >&2
}

fail() {
    printf 'error: %s\n' "$*" >&2
    exit 1
}

require_command() {
    local tool
    for tool in "$@"; do
        command -v "$tool" >/dev/null 2>&1 || fail "$tool is required but not installed"
    done
}

require_env() {
    local variable
    for variable in "$@"; do
        [ -n "${!variable:-}" ] || fail "$variable is not set"
    done
}

# Poll a check until it passes or the timeout runs out. Pass the check with its
# arguments, for example: wait_until "the delegation" delegation_is_live
wait_until() {
    local description="$1"
    local timeout_secs="$2"
    local interval_secs="$3"
    shift 3
    local started_secs="$SECONDS"
    local elapsed_secs=0
    while :; do
        if "$@"; then
            note "$description is ready after ${elapsed_secs}s"
            return 0
        fi
        if ((elapsed_secs >= timeout_secs)); then
            warn "$description did not appear within ${timeout_secs}s"
            return 1
        fi
        printf '    waiting for %s (%ss of %ss)\n' "$description" "$elapsed_secs" "$timeout_secs"
        sleep "$interval_secs"
        elapsed_secs=$((SECONDS - started_secs))
    done
}

# Join with a comma, because env.list reads the values that way.
comma_list() {
    local joined
    joined="$(IFS=,; printf '%s' "$*")"
    printf '%s' "$joined"
}

save_state() {
    local pair key temporary
    for pair in "$@"; do
        key="${pair%%=*}"
        printf -v "$key" '%s' "${pair#*=}"
    done
    UPDATED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    mkdir -p "$STATE_DIR"
    temporary="$(mktemp)"
    {
        printf '# State of the %s deployment. Written by deploy/provision.sh.\n' "$RELAY_HOSTNAME"
        printf '# Safe to delete: every step checks the resources themselves.\n'
        for key in "${STATE_KEYS[@]}"; do
            [ -n "${!key:-}" ] || continue
            printf '%s=%q\n' "$key" "${!key}"
        done
    } >"$temporary"
    mv "$temporary" "$STATE_FILE"
}

record_step() {
    local name="$1"
    local summary="$2"
    mkdir -p "$STEP_RECORD_DIR"
    printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$summary" >"$STEP_RECORD_DIR/$name"
}

# Record that a step found its work done, and stop without changing anything.
confirm_step() {
    local name="$1"
    local summary="$2"
    record_step "$name" "confirmed $summary"
    note "$summary"
    exit "$EXIT_SKIPPED"
}

read_step_record() {
    [ -f "$STEP_RECORD_DIR/$1" ] || return 1
    cat "$STEP_RECORD_DIR/$1"
}

# The deployment remembers its own hostname, so a rerun does not repeat it.
RELAY_HOSTNAME_REQUESTED="${RELAY_HOSTNAME:-}"
if [ -f "$STATE_FILE" ]; then
    # shellcheck source=/dev/null
    source "$STATE_FILE"
fi
if [ -n "$RELAY_HOSTNAME_REQUESTED" ] && [ "$RELAY_HOSTNAME_REQUESTED" != "${RELAY_HOSTNAME:-}" ]; then
    fail "$STATE_FILE belongs to ${RELAY_HOSTNAME:-}, but RELAY_HOSTNAME is $RELAY_HOSTNAME_REQUESTED. Delete $STATE_DIR to start over."
fi
RELAY_HOSTNAME="${RELAY_HOSTNAME_REQUESTED:-${RELAY_HOSTNAME:-relays.to}}"

SERVER_TYPE="${SERVER_TYPE:-ccx33}"
SERVER_IMAGE="${SERVER_IMAGE:-docker-ce}"
SERVER_LOCATION="${SERVER_LOCATION:-fsn1}"
SMTP_FLOATING_IP_COUNT="${SMTP_FLOATING_IP_COUNT:-2}"
S3_ENDPOINT="${S3_ENDPOINT:-fsn1.your-objectstorage.com}"
S3_REGION="${S3_REGION:-fsn1}"
S3_ENDPOINT_URL="${S3_ENDPOINT_URL:-https://$S3_ENDPOINT}"
S3_BUCKET="${S3_BUCKET:-relay-${RELAY_HOSTNAME//./-}}"
DEPLOY_KEY="${DEPLOY_KEY:-$DEPLOY_DIR/id_ed25519}"
DEPLOY_KEY_NAME="${RELAY_HOSTNAME}-deploy"
PUBLIC_RESOLVERS="${PUBLIC_RESOLVERS:-1.1.1.1 9.9.9.9}"
WAIT_TIMEOUT_SECS="${WAIT_TIMEOUT_SECS:-600}"
WAIT_INTERVAL_SECS="${WAIT_INTERVAL_SECS:-15}"

# Space separated inputs that a step iterates over.
read -ra SSH_PUBLIC_KEY_FILES <<<"${SSH_PUBLIC_KEY_FILES:-$HOME/.ssh/id_ed25519.pub}"
read -ra PUBLIC_RESOLVERS <<<"$PUBLIC_RESOLVERS"

AWS_DEFAULT_REGION="$S3_REGION"
export AWS_DEFAULT_REGION
