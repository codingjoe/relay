# Deploy Instructions

See `deploy/README.md` for the full checklist.

## Local stack

- `deploy/minikube` runs the full stack with `.env`. See `README.md`.

## Production

Deployment is driven by `.github/workflows/deploy.yml`.

- `kubectl apply -k deploy/k8s`. Apply the stack.
- `kubectl rollout status deployment/<name>`. Watch a workload.
- `kubectl logs deployment/<name>`. Read logs.
- `kubectl exec postgres-0 -- psql -U postgres`. Reach the database.

`kubectl` needs a kubeconfig. The provisioning step publishes one as the
`KUBECONFIG` secret. The admin kubeconfig is
`deploy/.state/talos/kubeconfig`. `talosctl kubeconfig --force --merge=false <path>`
re-issues it.

## Kubernetes manifests

- Keep manifests in `deploy/k8s/`, grouped by concern.
  `kustomization.yaml` lists them.
- Put multi-line config in real files and generate ConfigMaps from
  `kustomization.yaml`. The generated name carries a content hash, so edits
  roll the workload. A block scalar updates in place and leaves old pods.
- Do not probe run-to-completion Job containers. Their health signal is the
  Job condition.
- Give every container resource requests and limits.
- Add startup probes only where boot is slow: `msa`, `mta`, `clamav`,
  `postgres`. Elsewhere a liveness probe with a sensible `failureThreshold`
  is enough.
- Set `args`, not `command`, when overriding a service.
- Never put credentials in a ConfigMap. Use a `${PLACEHOLDER}` and render a
  Secret in the deploy workflow.
- Do not rely on `$(VAR)` expansion in manifests. Derive values in the
  workflow.
- Derive cluster-topology values in the deploy workflow, not
  `.env.production`. The database URL, Redis URLs, rspamd URL, and mail
  certificate paths are functions of Service names.
- Set `HOSTNAME` explicitly from the `relay-infra` Secret. Kubernetes sets it
  to the pod name, and relay reads it for the platform domain.
- The entrypoint decrypts the environment. It does not validate it. A missing
  key falls back to Django defaults.
- Do not add pod anti-affinity on a single node. Use
  `preferredDuringSchedulingIgnoredDuringExecution` when the cluster grows.
- Keep `postgres` and `redis-tasks` at one replica. Run one `crontask`.
- Mount `caddy-data` into the mail servers read-only. It holds the
  certificates.

## Provisioning steps

- Every step in `deploy/steps/` is safe to run twice. Check the resource
  before changing it. `deploy/provision.sh` stops at the first unfinished
  step.
- Destructive actions are opt-in flags, never part of a bare
  `./deploy/provision.sh`.
- Object storage credentials have two spellings. A step that shells out to
  the `aws` CLI calls `adopt_stored_s3_credentials` first.
