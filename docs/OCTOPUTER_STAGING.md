# Octoputer Staging Notes

O.P.E. will stage on the **Octoputer**, the user's k3s cluster.

## Source-of-truth repo for existing cluster conventions

Existing k3s conventions live in `DroneWuKong/Ai-Project`, especially:

- `infra/octo/RUNNERS.md`
- `infra/octo/minio/README.md`
- `.github/workflows/octo-minio-deploy.yml`

## Important inherited conventions

1. Cluster-mutating GitHub Actions jobs should run on a self-hosted runner labelled `octo-cp`.
2. The control-plane runner should have working `kubectl` access to the cluster.
3. The expected k3s kubeconfig path is `/etc/rancher/k3s/k3s.yaml`, unless overridden by a repo variable.
4. Build-pool runners and cluster-control runners are separate label concerns.
5. MinIO already has a deployment pattern under the `octo-ci` namespace; O.P.E. should use the same workflow style but its own `ope` namespace.

## O.P.E. staging namespace

```bash
kubectl apply -f k8s/namespace.yaml
```

## MVP services

For manual kubectl testing, create `ope-db` and `ope-provider-env` from a private
copy of `k8s/secrets.example.yaml` first. Do not apply the example file as-is.

```bash
kubectl apply -f k8s/postgres.yaml
kubectl apply -f k8s/redis.yaml
kubectl apply -f k8s/litellm.yaml
kubectl apply -f k8s/ope-core.yaml
```

## Manual Workflow

Use **Octo - Deploy OPE** in GitHub Actions for normal staging deploys. It runs
on `vars.OCTO_CP_RUNNER || '["self-hosted","octo-cp"]'`, creates `ope-db` and
`ope-provider-env` from GitHub secrets, applies manifests, runs
`migrations/001_initial_schema.sql`, and verifies `/health` plus `/ready` from
inside the cluster.

The deploy workflow defaults to `ghcr.io/dronewukong/ope-core:latest`, which is
published by **Build OPE Core Image** after pushes to `main`. For safer manual
staging, pass a specific tag or `sha-*` image to the deploy workflow input.

## Approval Policy

Tool routes are gated by `policies/approval-policy.yaml`. The current MVP uses a
request-level approval token (`tool_action_approved`) so `/plan` can explain a
tool route while `/ask` rejects unapproved tool actions before memory or model
side effects.

Approved tool-action asks enqueue `pending_review` rows in `tool_jobs`. Workers
can atomically claim `approved` jobs with leases, heartbeat while running, then
mark jobs `succeeded` or `failed`.

Use `/tools/queue/stats` to check pending review backlog, approved backlog,
running jobs, and expired leases before scaling tool runners.

`k8s/tool-runner.yaml` deploys the runner at `replicas: 0` by default. The
current runner only executes `noop` jobs and fails non-allowlisted tools.

## API Auth

`ope-core` requires bearer tokens in Octoputer (`OPE_REQUIRE_API_KEY=true`).
Set GitHub secret `OPE_API_KEYS` to one or more comma-separated API keys. Health
and readiness probes remain unauthenticated.

## To-do before real deployment

- Create provider environment values as GitHub Actions secrets, not repo files.
- Create `OPE_API_KEYS` as a GitHub Actions secret.
- Create Kubernetes secrets from the workflow at deploy time.
- Add an ingress or NodePort only after the internal service works.
- Decide whether O.P.E. should use the existing Octo MinIO for artifacts/log bundles.
