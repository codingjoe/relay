# Cluster add-ons

The three add-on manifests here are vendored verbatim from their pinned
upstream releases, so the bytes applied by `deploy/steps/10-cluster.sh` can be
checked against the tag they came from. `.pre-commit-config.yaml` excludes this
directory from `yamlfmt`, because a reformat would break that match.

- `local-path-storage.yaml`, from
  [rancher/local-path-provisioner](https://github.com/rancher/local-path-provisioner)
  at tag `v0.0.37`:
  <https://raw.githubusercontent.com/rancher/local-path-provisioner/v0.0.37/deploy/local-path-storage.yaml>
- `metrics-server.yaml`, from
  [kubernetes-sigs/metrics-server](https://github.com/kubernetes-sigs/metrics-server)
  at tag `v0.9.0`:
  <https://github.com/kubernetes-sigs/metrics-server/releases/download/v0.9.0/components.yaml>
- `kubelet-serving-cert-approver.yaml`, from
  [alex1989hu/kubelet-serving-cert-approver](https://github.com/alex1989hu/kubelet-serving-cert-approver)
  at tag `v0.12.1`:
  <https://raw.githubusercontent.com/alex1989hu/kubelet-serving-cert-approver/v0.12.1/deploy/standalone-install.yaml>

`kustomization.yaml` is local. It lists the manifests above plus `namespace.yaml`,
which labels `default` for relay's privileged pods, and carries the patches that
move local-path storage to `/var/local-path-provisioner` and admit the privileged
helper pods.

A bump from Dependabot moves one `image:` line, which leaves the file no longer
matching its release. Re-vendor the whole manifest, then update the link above
and the URL in `.github/workflows/ci.yml`.
