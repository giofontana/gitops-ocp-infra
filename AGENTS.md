# AGENTS.md — gitops-ocp-infra

This repository manages a home lab of OpenShift clusters using **ArgoCD-based GitOps**. All cluster state — operators, workloads, configuration, and governance policies — is declared in YAML manifests and reconciled automatically by ArgoCD.

## Repository layout

```
gitops/manifests/
├── operators/              # Operator subscriptions and instances (base + overlays)
├── workloads/              # Application workloads (base + overlays)
├── clusters/
│   ├── all/                # Shared across every cluster
│   │   ├── bootstrap/      # App-of-Apps entrypoints (apply once per cluster)
│   │   ├── aggregate/      # Kustomizations that compose operator + config
│   │   └── configuration/  # Shared runtime config (auth, gitops admin group)
│   ├── simpsons/           # Primary full-featured cluster
│   ├── flanders/           # Secondary cluster (managed from simpsons ArgoCD)
│   ├── ocp1/ ocp2/ ocp3/  # Lightweight clusters
│   └── <cluster>/
│       ├── bootstrap/stable/       # Cluster-specific App-of-Apps
│       ├── apps/infra/stable/      # ArgoCD Application manifests for infra
│       ├── apps/workloads/stable/  # ArgoCD Application manifests for workloads
│       ├── apps/wip/              # Work-in-progress apps (not yet promoted)
│       ├── aggregate/<category>/   # Kustomizations combining operator + config
│       └── configuration/          # Cluster-specific runtime resources
├── wip/                    # Scratch / experimental manifests not managed by ArgoCD
governance/policies/        # ACM governance policies for multi-cluster compliance
ansible/                    # Infrastructure automation (Dell hardware, node drain)
python/                     # Cluster power management scripts
```

## Core concepts

### App-of-Apps pattern

ArgoCD is bootstrapped with a top-level Application that points to a directory of child Application manifests. This fans out into all managed components.

**Bootstrap chain:**
1. `clusters/all/bootstrap/stable/` — shared App-of-Apps (infra operators common to all clusters)
2. `clusters/<cluster>/bootstrap/stable/` — cluster-specific App-of-Apps (infra + workloads for that cluster)

Each child Application points to an **aggregate** directory.

### Aggregation layer

An aggregate kustomization composes two things:
- The **operator or workload** manifests (from `operators/` or `workloads/`, via a specific overlay)
- The **cluster-specific configuration** (from `clusters/<cluster>/configuration/`)

Example (`clusters/simpsons/aggregate/infra/metallb/kustomization.yaml`):
```yaml
resources:
  - ../../../../../operators/metallb/overlays/default     # operator subscription + instance
  - ../../../configuration/metallb                        # cluster-specific IP pools
```

This separation lets the same operator definition be reused across clusters with different runtime configuration.

### Base / overlay structure

Both operators and workloads follow Kustomize base/overlay convention:

```
operators/<name>/
├── base/                   # (optional) raw manifests
└── overlays/
    ├── default/            # standard config
    ├── stable/             # pinned channel
    └── latest/             # bleeding-edge channel

workloads/<name>/
├── base/                   # core manifests (namespace, deployment, service, etc.)
└── overlays/
    ├── stable/
    └── cpu/                # variant (e.g., CPU-only vs GPU)
```

Some operators pull their base from a remote `gitops-catalog` repository instead of a local `base/` directory:
```yaml
resources:
  - github.com/giofontana/gitops-catalog/metallb-operator/operator/overlays/stable
```

### Sync waves

ArgoCD sync-wave annotations control deployment order:
- Operators and their CRDs deploy at lower waves (e.g., `sync-wave: "1"`)
- Instance/CR resources deploy at higher waves (e.g., `sync-wave: "5"`)
- Workloads typically use `sync-wave: "5"` or higher

Always set `argocd.argoproj.io/sync-options: SkipDryRunOnMissingResource=true` when a resource depends on a CRD that is installed by a different sync wave.

## Secret management

Secrets are encrypted with **Bitnami Sealed Secrets**. The sealed-secrets-operator runs on each cluster and decrypts `SealedSecret` resources into regular `Secret` objects.

- Sealed secret files are named `*-sealed.yaml` and are safe to commit
- Never commit plain `Secret` YAML — always seal it first with `kubeseal`
- The encryption key is cluster-specific; the backup/restore scripts are in `operators/sealed-secrets-operator/scripts/`

## How to add a new operator

1. **Create the operator directory** at `operators/<name>/overlays/<variant>/kustomization.yaml` referencing either a local `base/` or a remote `gitops-catalog` URL
2. **Create cluster configuration** at `clusters/<cluster>/configuration/<name>/` with any instance CRs, IP pools, storage classes, etc.
3. **Create the aggregate** at `clusters/<cluster>/aggregate/infra/<name>/kustomization.yaml` that combines step 1 and step 2
4. **Create the ArgoCD Application** at `clusters/<cluster>/apps/infra/stable/<name>.yaml` pointing to the aggregate path
5. **Register in App-of-Apps** — add the new Application YAML to the cluster's `apps/infra/stable/kustomization.yaml`

Use an existing operator like `metallb` as a template.

## How to add a new workload

1. **Create the workload directory** at `workloads/<name>/base/` with namespace, deployment, service, route, PVCs, etc.
2. **Create overlays** at `workloads/<name>/overlays/<variant>/` for environment-specific patches
3. **Create cluster configuration** (if needed) at `clusters/<cluster>/configuration/<name>/` for certs, secrets, etc.
4. **Create the aggregate** at `clusters/<cluster>/aggregate/workloads/<name>/kustomization.yaml`
5. **Create the ArgoCD Application** at `clusters/<cluster>/apps/workloads/stable/<name>.yaml`
6. **Register in App-of-Apps** — add to `clusters/<cluster>/apps/workloads/stable/kustomization.yaml`

Use an existing workload like `frigate` as a template.

## How to promote WIP to stable

Items under `apps/wip/` or `wip/` are not synced by ArgoCD until moved into the stable path:
1. Move the Application YAML from `apps/wip/` to `apps/infra/stable/` or `apps/workloads/stable/`
2. Add the file to the corresponding `kustomization.yaml`
3. Commit to `main` — ArgoCD auto-syncs

## ArgoCD Application conventions

Every Application manifest follows this pattern:
```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: <component-name>
  annotations:
    argocd.argoproj.io/compare-options: IgnoreExtraneous
  labels:
    gitops.ownedBy: default
spec:
  destination:
    namespace: openshift-gitops       # or argocd-workloads for workload apps
    server: https://kubernetes.default.svc
  project: default
  source:
    path: gitops/manifests/clusters/<cluster>/aggregate/<category>/<name>/
    repoURL: https://github.com/giofontana/gitops-ocp-infra.git
    targetRevision: main
  syncPolicy:
    automated:
      prune: false
      selfHeal: true
```

Key fields:
- `destination.namespace`: `openshift-gitops` for infra, `argocd-workloads` for workloads
- `prune: false` is the default — ArgoCD will not delete resources removed from git without manual intervention
- `selfHeal: true` — drift from git is auto-corrected

## Git workflow

- **Single branch**: `main` is the only deployment branch. ArgoCD watches `main` and auto-syncs.
- **All changes go through `main`**: commit and push to trigger reconciliation. There are no environment branches.
- **No CI pipeline enforces validation** — manually verify manifests with `oc apply --dry-run=client -k <path>` or `kustomize build <path>` before pushing.

## Validation

Before committing changes, verify manifests render correctly:
```bash
# Validate a kustomization
kustomize build gitops/manifests/clusters/<cluster>/aggregate/<category>/<name>/

# Dry-run against the cluster
oc apply --dry-run=client -k gitops/manifests/clusters/<cluster>/aggregate/<category>/<name>/
```

## Important guardrails

- **Never commit plain secrets.** Use `kubeseal` to produce `SealedSecret` resources.
- **Respect sync-wave ordering.** Operators and CRDs must deploy before their instances.
- **Keep `prune: false` unless explicitly intended.** Enabling prune means ArgoCD will delete resources you remove from git.
- **Test kustomize builds locally.** A broken kustomization will cause ArgoCD sync failures.
- **Use `SkipDryRunOnMissingResource=true`** on resources that depend on CRDs from other sync waves.
- **Remote bases from `gitops-catalog`** are pinned by path, not by tag — be aware that upstream changes can affect builds.
