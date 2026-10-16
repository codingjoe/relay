# Open the production Dozzle dashboard.
dozzle:
    #!/usr/bin/env bash
    set -euo pipefail
    export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/relay.yaml}"
    kubectl port-forward svc/dozzle 5000:8080 &
    trap 'kill "$!" 2>/dev/null || true' EXIT
    until curl -fs --max-time 5 -o /dev/null http://127.0.0.1:5000 2>/dev/null; do
        kill -0 "$!" 2>/dev/null || exit 1
        sleep 0.1
    done
    open http://127.0.0.1:5000
    wait

# Open the production Threadmill inspector.
threadmill:
    TASK_REDIS_URL="rediss://:$(dotenvx get REDIS_PASSWORD -f .env.production)@redis-tasks.$(dotenvx get HOSTNAME -f .env.production):443" uv run --group=dev python manage.py threadmill inspector

# Install the newest cluster-access kubeconfig as ~/.kube/relay.yaml.
access:
    #!/usr/bin/env bash
    set -euo pipefail

    die() {
        printf 'production access: %s\n' "$*" >&2
        exit 1
    }

    require_command() {
        command -v "$1" >/dev/null 2>&1 || die "$1 is required but not installed"
    }

    require_command gh
    require_command age

    login="$(gh api user --jq .login)"

    identities=()
    for key in "$HOME/.ssh/id_ed25519" "$HOME/.ssh/id_rsa"; do
        if [ -f "$key" ]; then
            identities+=(-i "$key")
        fi
    done
    [ "${#identities[@]}" -gt 0 ] ||
        die "no SSH private key at ~/.ssh/id_ed25519 or ~/.ssh/id_rsa, so age cannot open your file"

    SCRATCH="$(mktemp -d)"
    trap 'rm -rf "$SCRATCH"' EXIT

    default_branch="$(gh repo view --json defaultBranchRef --jq .defaultBranchRef.name)"
    run_id="$(gh run list --workflow cluster-access.yml --branch "$default_branch" \
        --status success --limit 1 --json databaseId --jq '.[0].databaseId')"
    case "$run_id" in
        "" | null)
            die "no successful cluster-access run on $default_branch, so there is nothing to install"
            ;;
    esac
    gh run download "$run_id" --name cluster-access --dir "$SCRATCH"

    kubeconfig_artifact="$SCRATCH/$login-kubeconfig.age"
    [ -f "$kubeconfig_artifact" ] ||
        die "the newest cluster-access artifact holds no kubeconfig for $login, add an SSH key on GitHub and wait for the next run"

    umask 077
    mkdir -p "$HOME/.kube"
    age --decrypt "${identities[@]}" "$kubeconfig_artifact" > "$SCRATCH/kubeconfig"
    install -m 600 "$SCRATCH/kubeconfig" "$HOME/.kube/relay.yaml"

    printf 'export KUBECONFIG="%s/.kube/relay.yaml"\n' "$HOME"
