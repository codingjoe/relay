#!/usr/bin/env bash
#
# Provision relay on a single Hetzner Cloud server.
#
# Every step is a script of its own in deploy/steps/. This entry point runs
# them in order and stops at the first step that is not done, so a rerun picks
# up where the last run stopped:
#
#   ./deploy/provision.sh           run every step that is not done yet
#   ./deploy/provision.sh records   run one step, by name
#   ./deploy/provision.sh --status  show what is done, what is pending, and when
#   ./deploy/provision.sh --list    list the steps in order
#
# Every step checks the resource it manages before it changes anything, so
# running it twice is safe.
#
# See deploy/README.md for the operator guide and deploy/config.sh for the
# inputs.

set -euo pipefail

PROVISION_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=config.sh
source "$PROVISION_DIR/config.sh"

usage() {
    cat <<'EOF'
Usage:
  provision.sh              run every step that is not done yet
  provision.sh <step>...    run the given steps
  provision.sh --status     show what is done and what is pending
  provision.sh --list       list the steps in order
EOF
}

step_name() {
    local file="${1##*/}"
    file="${file%.sh}"
    printf '%s' "${file#*-}"
}

find_step() {
    local path
    for path in "$PROVISION_DIR"/steps/*.sh; do
        if [ "$(step_name "$path")" = "$1" ]; then
            printf '%s' "$path"
            return 0
        fi
    done
    return 1
}

list_steps() {
    local path
    for path in "$PROVISION_DIR"/steps/*.sh; do
        printf '%s\n' "$(step_name "$path")"
    done
}

show_status() {
    local path name record status
    printf '%-13s %-8s %s\n' step state recorded
    for path in "$PROVISION_DIR"/steps/*.sh; do
        name="$(step_name "$path")"
        record="$(read_step_record "$name" || true)"
        if "$path" --check >/dev/null 2>&1; then
            status="done"
        else
            status="pending"
        fi
        printf '%-13s %-8s %s\n' "$name" "$status" "${record:--}"
    done
}

run_step() {
    local path="$1"
    local name status=0
    name="$(step_name "$path")"
    log "$name"
    "$path" || status=$?
    case "$status" in
        0) ;;
        "$EXIT_SKIPPED")
            printf '    nothing to do\n'
            return 0
            ;;
        "$EXIT_INCOMPLETE")
            printf '\nerror: %s is waiting for you, see the notes above\n' "$name" >&2
            ;;
        *)
            printf '\nerror: %s failed with status %s\n' "$name" "$status" >&2
            ;;
    esac
    return "$status"
}

# A step that is still pending after a full run needs the operator, so the run
# reports that with the same status an incomplete step returns.
count_pending_steps() {
    local path pending=0
    for path in "$PROVISION_DIR"/steps/*.sh; do
        "$path" --check >/dev/null 2>&1 || pending=$((pending + 1))
    done
    printf '%s' "$pending"
}

run_all() {
    local path pending status=0
    for path in "$PROVISION_DIR"/steps/*.sh; do
        run_step "$path" || {
            status=$?
            break
        }
    done
    printf '\n'
    show_status
    pending="$(count_pending_steps)"
    if [ "$pending" -eq 0 ]; then
        printf '\nEvery step is done.\n'
        return "$status"
    fi
    printf '\n%s steps are still pending, see the table above.\n' "$pending"
    if [ "$status" -eq 0 ]; then
        status="$EXIT_INCOMPLETE"
    fi
    return "$status"
}

case "${1:-}" in
    --help | -h)
        usage
        ;;
    --list | -l)
        list_steps
        ;;
    --status | -s)
        show_status
        ;;
    "")
        run_all
        ;;
    *)
        for name in "$@"; do
            if ! path="$(find_step "$name")"; then
                fail "no step named $name. Run ./deploy/provision.sh --list"
            fi
            run_step "$path"
        done
        ;;
esac
