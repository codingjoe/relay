#!/usr/bin/env bash
#
# Provisioning step: install the cluster add-ons Talos does not bundle.
#
# Inputs: the admin kubeconfig at $TALOS_DIR/kubeconfig, written by the
#         environment step.

set -euo pipefail

STEPS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../config.sh
source "$(dirname "$STEPS_DIR")/config.sh"

TALOS_DIR="${TALOS_DIR:-$STATE_DIR/talos}"
KUBECONFIG_FILE="$TALOS_DIR/kubeconfig"

kubectl_admin() {
    kubectl --kubeconfig "$KUBECONFIG_FILE" "$@"
}

deployment_is_available() {
    local desired available
    desired="$(kubectl_admin -n "$1" get deployment "$2" -o jsonpath='{.spec.replicas}' 2>/dev/null)" || return 1
    available="$(kubectl_admin -n "$1" get deployment "$2" -o jsonpath='{.status.availableReplicas}' 2>/dev/null)"
    [ "$desired" = "${available:-0}" ]
}

# The kubelet-serving-cert-approver is what lets metrics-server skip
# --kubelet-insecure-tls: the machine config turns on serverTLSBootstrap, and
# until the approver signs the kubelet serving CSRs, the kubelet answers with a
# self-signed certificate that metrics-server refuses to trust.
cluster_addons_are_ready() {
    [ -f "$KUBECONFIG_FILE" ] || return 1
    deployment_is_available local-path-storage local-path-provisioner || return 1
    deployment_is_available kube-system metrics-server || return 1
    deployment_is_available kubelet-serving-cert-approver kubelet-serving-cert-approver || return 1
    kubectl_admin get namespace local-path-storage \
        -o jsonpath='{.metadata.labels.pod-security\.kubernetes\.io/enforce}' 2>/dev/null |
    grep -q '^privileged$' || return 1
    kubectl_admin get configmap local-path-config -n local-path-storage \
        -o jsonpath='{.data.config\.json}' 2>/dev/null |
    grep -q '"/var/local-path-provisioner"'
}

if [ "${1:-}" = "--check" ]; then
    cluster_addons_are_ready
    exit "$?"
fi

require_command kubectl
[ -f "$KUBECONFIG_FILE" ] ||
fail "no admin kubeconfig at $KUBECONFIG_FILE. Run ./deploy/provision.sh environment first"

# Always apply: the readiness check cannot tell whether the pinned manifests
# are the ones deployed, so a bumped pin would otherwise never land.
note "Applying the pinned add-ons in deploy/cluster"
kubectl_admin apply -k "$DEPLOY_DIR/cluster"

if ! wait_until "the cluster add-ons" cluster_addons_are_ready; then
    warn "the add-ons did not become ready within ${WAIT_TIMEOUT_SECS}s. See what they say:"
    warn "  kubectl --kubeconfig $KUBECONFIG_FILE get pods -n local-path-storage"
    warn "  kubectl --kubeconfig $KUBECONFIG_FILE get pods -n kube-system -l k8s-app=metrics-server"
    warn "  kubectl --kubeconfig $KUBECONFIG_FILE get pods -n kubelet-serving-cert-approver"
    exit "$EXIT_INCOMPLETE"
fi

record_step cluster "applied the local-path, metrics-server and kubelet-serving-cert-approver add-ons"

note "Dozzle reads CPU and memory from metrics.k8s.io. Check the source with:"
note "  kubectl --kubeconfig $KUBECONFIG_FILE top nodes"
