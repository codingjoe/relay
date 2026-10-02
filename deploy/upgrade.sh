#!/usr/bin/env bash
#
# Maintenance step: move the node to the Talos release named by TALOS_INSTALLER.
#
# The OS upgrade installs from the Image Factory installer image, so the
# platform schematic survives, and Kubernetes moves to the release
# KUBERNETES_VERSION pins, which is the one TALOS_VERSION ships: upgrade-k8s
# takes an explicit --to, so a talosctl binary from another release cannot move
# the cluster to its own default. Both act on the node, and mail retries cover
# the gap.
#
# Hetzner's own status gates the run. An unresolved incident, or a maintenance
# that overlaps the window, skips the upgrade; a status that cannot be read
# fails it. A scheduled run only acts inside Wednesday 01:00-03:00 UTC, a manual
# one may act outside that window.
#
# Usage: TALOS_INSTALLER=<installer image> deploy/upgrade.sh [--scheduled]
#
# Inputs:
#   TALOS_INSTALLER  Image Factory installer image (CI: the TALOS_INSTALLER
#                    repository variable)
#   TALOS_ENDPOINT   address of the node (CI: the TALOS_ENDPOINT repository
#                    variable, the recorded SERVER_ADDRESS otherwise)
#   KUBERNETES_VERSION Kubernetes release to upgrade to, pinned in config.sh
#   TALOSCONFIG      path of the talosconfig (deploy/.state/talos/talosconfig)
#   KUBECONFIG       kubeconfig used to verify the workloads (CI: the
#                    KUBECONFIG repository secret)
#
# See deploy/README.md for the operator guide.

set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=config.sh
source "$DEPLOY_DIR/config.sh"

case "${1:-}" in
    --scheduled | "") ;;
    *) fail "usage: $(basename "$0") [--scheduled]" ;;
esac

# CI passes the endpoint and the installer as repository variables; a local run
# takes them from the recorded state and config.sh.
export TALOSCONFIG="${TALOSCONFIG:-$TALOS_DIR/talosconfig}"
# shellcheck disable=SC2154 # SERVER_ADDRESS is recorded in the state file
export TALOS_ENDPOINT="${TALOS_ENDPOINT:-${SERVER_ADDRESS:-}}"
require_env TALOS_ENDPOINT TALOS_INSTALLER
require_command talosctl kubectl python3

# status.hetzner.com has no API: the page is a static Next.js app that embeds
# its incidents as __NEXT_DATA__, so the gate reads that. It prints the reason
# to skip, and nothing at all when the status is clear.
# todo: keep scraping __NEXT_DATA__ until Hetzner publishes a status API
skip_reason="$(python3 - "${1:-}" <<'PY'
import datetime
import json
import re
import sys
import urllib.request

scheduled = sys.argv[1] == "--scheduled"
now = datetime.datetime.now(datetime.timezone.utc)
window_start = now.replace(hour=1, minute=0, second=0, microsecond=0)
window_end = now.replace(hour=3, minute=0, second=0, microsecond=0)
if scheduled:
    if not window_start <= now < window_end:
        print(f"the run starts at {now:%H:%M} UTC, outside the 01:00-03:00 window")
        sys.exit(0)
else:
    # A manual run acts now, so the maintenance check looks two hours ahead,
    # the time a scheduled upgrade takes.
    window_start, window_end = now, now + datetime.timedelta(hours=2)

try:
    with urllib.request.urlopen("https://status.hetzner.com/", timeout=30) as response:
        page = response.read().decode()
    embedded = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', page, re.S)
    incidents = json.loads(embedded.group(1))["props"]["pageProps"]["incidents"]

    # topNotification carries the current incident, informationList the
    # announcements, maintenanceList the scheduled work and incidentHistory
    # everything resolved. Anything unresolved that is neither an announcement
    # nor a maintenance blocks the upgrade; a maintenance only when its window
    # meets ours.
    blocking = []
    for item in [entry for entries in incidents.values() for entry in entries]:
        if item["incidentType"] == "other" or item["incidentState"] in ("resolved", "completed"):
            continue
        if item["incidentType"] == "maintenance":
            starts = datetime.datetime.fromisoformat(item["startTime"])
            ends = item["endTime"] and datetime.datetime.fromisoformat(item["endTime"])
            if starts > window_end or (ends and ends < window_start):
                continue
        blocking.append(f'{item["incidentType"]} "{item["titleEn"]}" ({item["incidentState"]})')
except Exception as error:
    print(f"::error::cannot read status.hetzner.com: {error}", file=sys.stderr)
    sys.exit(1)

if blocking:
    print("Hetzner reports " + ", ".join(blocking))
PY
)"

if [ -n "$skip_reason" ]; then
    printf '::notice::skipping the upgrade: %s\n' "$skip_reason"
    exit 0
fi

# The image tag names the Talos release the node has to run.
target_version="${TALOS_INSTALLER##*:}"

# The last Tag: line belongs to the node, the one before it to the client.
node_version() {
    talosctl -n "$TALOS_ENDPOINT" version |
    sed -n 's/^[[:space:]]*Tag:[[:space:]]*//p' |
    tail -1
}

current_version="$(node_version)"
if [ "$current_version" = "$target_version" ]; then
    note "the node already runs Talos $target_version"
else
    log "upgrading Talos from $current_version to $target_version"
    talosctl -n "$TALOS_ENDPOINT" upgrade --image "$TALOS_INSTALLER"
fi

# Kubernetes has a version of its own and a run can die between it and the OS
# upgrade, so it always runs: upgrade-k8s is failure-safe to re-run. The target
# is the pinned Kubernetes release, never the one the client binary defaults to,
# so a drifted talosctl cannot move the cluster off it.
log "upgrading Kubernetes to $KUBERNETES_VERSION"
talosctl -n "$TALOS_ENDPOINT" upgrade-k8s --to "$KUBERNETES_VERSION"

log "verifying the node and the workloads"
verified_version="$(node_version)"
[ "$verified_version" = "$target_version" ] ||
fail "the node reports Talos $verified_version after the upgrade, expected $target_version"
note "the node runs Talos $verified_version"

# A namespace with no pods passes the filter below, and so would a namespace
# whose workloads never came back, so the workloads the deploy leaves behind are
# asserted first: every Deployment and StatefulSet has to report all of its
# replicas ready, and a namespace that holds none fails outright.
# todo: a workload deleted from the cluster is invisible here; compare against
# the manifests in deploy/k8s if a partial cluster has to fail the run too
workloads_are_ready() {
    kubectl get deployment,statefulset --namespace relay \
        --output jsonpath='{range .items[*]}{.spec.replicas}{" "}{.status.readyReplicas}{"\n"}{end}' |
    awk '{ if (NF != 2 || $1 != $2) bad = 1 } END { exit (NR == 0 || bad) }'
}

pods_are_ready() {
    workloads_are_ready || return 1
    kubectl get pods --namespace relay --no-headers --field-selector=status.phase!=Succeeded |
    awk '$3 == "Terminating" || $3 == "Completed" { next }
         $2 != "1/1" || $3 != "Running" { exit 1 }'
}

wait_until "every relay workload" pods_are_ready ||
fail "the relay workloads did not come back; inspect kubectl get pods --namespace relay"

note "Talos $target_version and Kubernetes $KUBERNETES_VERSION are installed and the relay workloads are ready"
