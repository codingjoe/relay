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
#   SERVER_LOCATION         (fsn1)                   hcloud location
#   SMTP_FLOATING_IP_COUNT  (2)                      size of the SMTP egress pool
#   S3_BUCKET               (relay-<hostname with dots replaced by dashes>)
#   SSH_PUBLIC_KEY_FILES    (~/.ssh/id_ed25519.pub)  space separated
#   DEPLOY_KEY              (deploy/id_ed25519)
#
# See deploy/README.md for the operator guide.

# A step returns these instead of failing: provision.sh reports them and stops.
EXIT_SKIPPED=10
EXIT_INCOMPLETE=11

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$DEPLOY_DIR")"

# gh, dotenvx and the deployment workflow all resolve the repository from the
# working directory.
cd "$REPO_ROOT" || exit 1

STATE_DIR="$DEPLOY_DIR/.state"
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
    shift
    # A stray argument here would otherwise be run as a command, fail every
    # time, and spend the whole timeout looking like an unreachable resource.
    command -v "${1:-}" >/dev/null 2>&1 ||
    fail "wait_until was given \"${1:-}\", which is not a check it can run"
    local started_secs="$SECONDS"
    local elapsed_secs=0
    while :; do
        if "$@"; then
            note "$description is ready after ${elapsed_secs}s"
            return 0
        fi
        if ((elapsed_secs >= WAIT_TIMEOUT_SECS)); then
            warn "$description did not appear within ${WAIT_TIMEOUT_SECS}s"
            return 1
        fi
        printf '    waiting for %s (%ss of %ss)\n' "$description" "$elapsed_secs" "$WAIT_TIMEOUT_SECS"
        sleep "$WAIT_INTERVAL_SECS"
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
SERVER_LOCATION="${SERVER_LOCATION:-fsn1}"
SMTP_FLOATING_IP_COUNT="${SMTP_FLOATING_IP_COUNT:-2}"
S3_BUCKET="${S3_BUCKET:-relay-${RELAY_HOSTNAME//./-}}"
DEPLOY_KEY="${DEPLOY_KEY:-$DEPLOY_DIR/id_ed25519}"
DEPLOY_KEY_NAME="${RELAY_HOSTNAME}-deploy"

# The single server runs Hetzner's docker-ce image and keeps its bucket in the
# same location.
SERVER_IMAGE="docker-ce"
S3_REGION="fsn1"
S3_ENDPOINT_URL="https://fsn1.your-objectstorage.com"

# Caddy serves stored message bodies on this name, which the zone's wildcard
# record covers.
STORAGE_HOSTNAME="storage.$RELAY_HOSTNAME"

# Two unrelated resolvers, so a delegation or a record has to be live in public
# DNS rather than in one cache. A registrar change and a cached negative answer
# both settle in minutes, so the waits give them ten before they hand the work
# back to the operator.
PUBLIC_RESOLVERS=(1.1.1.1 9.9.9.9)
WAIT_TIMEOUT_SECS=600
WAIT_INTERVAL_SECS=15

read -ra SSH_PUBLIC_KEY_FILES <<<"${SSH_PUBLIC_KEY_FILES:-$HOME/.ssh/id_ed25519.pub}"

AWS_DEFAULT_REGION="$S3_REGION"
export AWS_DEFAULT_REGION
