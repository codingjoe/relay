# Development and operations recipes for relay.

# The image the minikube overlay runs.
development_image := "ghcr.io/codingjoe/relay:local"

# The port the local web UI is forwarded to.
web_port := "8000"

# The CLI tools the recipes shell out to. uv ships uvx, which runs prek.
binaries := "uv pnpm age gh dotenvx kubectl minikube"

# Every workload that runs the relay image.
relay_workloads := "deployment/web deployment/worker deployment/sender deployment/crontask deployment/dns deployment/msa deployment/mta"

# Production operations.
[group('production')]
mod production

# List the recipes.
default:
    @just --list

# Build the development image from the local .env.
[group('local')]
build-image:
    docker build \
        --target development \
        --build-arg UV_NO_DEV=0 \
        --build-arg DISTROLESS_FLAVOR=debug-nonroot \
        --build-arg DOTENV_FILE=.env \
        -t {{development_image}} .

# Start minikube and enable the metrics API Dozzle needs.
[group('local')]
start-cluster:
    minikube start
    minikube addons enable metrics-server

# Load the development image into minikube.
[group('local')]
load-image:
    minikube image load {{development_image}}

# Apply the minikube overlay and run the database migrations.
[group('local')]
migrate:
    kubectl -n default delete job migration --ignore-not-found
    kubectl apply -k deploy/minikube
    kubectl -n default wait --for=condition=complete job/migration --timeout=5m \
        || { kubectl -n default logs job/migration --tail=50; exit 1; }

# Rebuild the image and restart every relay workload.
[group('local')]
reload: build-image load-image
    kubectl -n default rollout restart {{relay_workloads}}

# Start the whole stack on minikube and open the web UI.
[group('local')]
dev: build-image start-cluster load-image migrate
    #!/usr/bin/env bash
    set -euo pipefail
    kubectl -n default rollout status deployment/web --timeout=5m
    kubectl port-forward svc/web {{web_port}}:8000 &
    trap 'kill "$!" 2>/dev/null || true' EXIT
    until curl -fsS -o /dev/null "http://127.0.0.1:{{web_port}}" 2>/dev/null; do
        kill -0 "$!" 2>/dev/null || exit 1
        sleep 0.2
    done
    printf 'relay is up at http://localhost:%s\n' "{{web_port}}"
    open "http://localhost:{{web_port}}" 2>/dev/null || true
    wait

# Run the local Django server on a free port.
[group('local')]
serve:
    uv run --env-file .env manage.py runserver "localhost:$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"

# Install the binaries, the dependencies and the git hooks.
[group('quality')]
install: install-binaries
    uv sync
    pnpm install
    uvx prek install

# Install the missing binaries with Homebrew.
[group('quality')]
[macos]
install-binaries:
    #!/usr/bin/env bash
    set -euo pipefail

    missing=()
    for binary in {{binaries}}; do
        command -v "$binary" >/dev/null 2>&1 || missing+=("$binary")
    done

    if [ "${#missing[@]}" -eq 0 ]; then
        printf 'all binaries are installed\n'
        exit 0
    fi

    printf 'installing with Homebrew: %s\n' "${missing[*]}"
    brew install "${missing[@]}"

# Report the binaries to install with your package manager.
[group('quality')]
[linux]
install-binaries:
    #!/usr/bin/env bash
    set -euo pipefail

    missing=()
    for binary in {{binaries}}; do
        command -v "$binary" >/dev/null 2>&1 || missing+=("$binary")
    done

    if [ "${#missing[@]}" -gt 0 ]; then
        printf 'missing binaries: %s\n' "${missing[*]}" >&2
        exit 1
    fi

    printf 'all binaries are installed\n'

# Build the CSS and the vendored ES modules.
[group('quality')]
build-assets:
    pnpm run build

# Rebuild the CSS and the vendored ES modules on change.
[group('quality')]
watch-assets:
    pnpm run dev

# Run the test suite.
[group('quality')]
test:
    uv run --group test pytest

# Run the Django system checks.
[group('quality')]
check:
    uv run python manage.py check

# Generate migrations for changed models.
[group('database')]
migrations:
    uv run python manage.py makemigrations

# Delete every migration file, so you can regenerate them from scratch.
[group('database')]
clear-migrations:
    #!/usr/bin/env bash
    set -euo pipefail
    shopt -s nullglob
    files=(*/migrations/[!_]*.py* services/email/*/migrations/[!_]*.py*)
    if [ "${#files[@]}" -eq 0 ]; then
        printf 'clear-migrations: no migration files found\n' >&2
        exit 1
    fi
    rm "${files[@]}"

# Regenerate the migrations and mark them applied without touching the schema.
[group('database')]
squash-migrations:
    : "${LOCAL_TABLE_NAME:?set LOCAL_TABLE_NAME to the local database}"
    psql "$LOCAL_TABLE_NAME" -a -c "TRUNCATE TABLE django_migrations"
    just migrations
    uv run python manage.py migrate --fake --no-input

# Recreate the local database from the test bundle.
[group('database')]
seed:
    rm -f db.sqlite3
    uv run --env-file .env manage.py migrate --noinput
    uv run --env-file .env manage.py loaddata fixtures/initial_data.yaml

# Dump the local database into the test bundle.
[group('database')]
dump-fixtures:
    uv run --env-file .env manage.py dumpdata auth accounts kms domains msa \
        --format yaml --output fixtures/initial_data.yaml
