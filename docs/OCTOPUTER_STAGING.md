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
kubectl apply -f k8s/ingress.yaml
```

## Manual Workflow

Use **Octo - Deploy OPE** in GitHub Actions for normal staging deploys. It runs
on `vars.OCTO_CP_RUNNER || '["self-hosted","octo-cp"]'`, creates `ope-db` and
`ope-provider-env` from GitHub secrets, applies manifests, runs
`migrations/001_initial_schema.sql`, verifies `/health` plus `/ready` from the
O.P.E. container, and verifies the tailnet-facing NodePorts from the runner.

The staging services intentionally expose stable NodePorts for small tailnet
clients such as Hangar Hub:

- O.P.E. Core: `http://<octoputer-node>:30080`
- LiteLLM: `http://<octoputer-node>:30400`

Health and readiness stay open on O.P.E. Core. Other O.P.E. routes require
`Authorization: Bearer <ope-api-key>` when `OPE_REQUIRE_API_KEY=true`.

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

## Tailnet URL

O.P.E. Core is reachable directly through the k3s NodePort on worker nodes:

- `http://100.81.235.34:30080`
- `http://100.77.146.94:30080`

LiteLLM is exposed for operator checks through:

- `http://100.81.235.34:30400`
- `http://100.77.146.94:30400`

The control-plane laptop (`octo-a`, `100.65.161.67`) advertises its LAN IP to
k3s, so native NodePort forwarding from that node can hang when the O.P.E. pods
run on worker tailnet nodes. Old clients may still be pinned to `octo-a`, so it
uses local systemd TCP bridges instead of user-level `kubectl port-forward`
services:

- `http://100.65.161.67:30080` -> `http://100.81.235.34:30080`
- `http://100.65.161.67:30400` -> `http://100.81.235.34:30400`

If those bridges need repair on `octo-a`, run:

```bash
ops/octo/install-ope-tailnet-bridge.sh
```

That installer disables the legacy user services `ope-core-forward.service` and
`ope-litellm-forward.service`, installs `/usr/local/bin/ope-tailnet-bridge.py`,
and creates persistent system services for both O.P.E. ports. It also inserts a
narrow NAT bypass for `tailscale0` before k3s NodePort rules so Kubernetes does
not steal packets meant for the local bridge.

Traefik ingress is installed for the future host routes:

- `http://ope.100.81.235.34.sslip.io`
- `https://ope.100.81.235.34.sslip.io`

The direct NodePort is the current supported staging path for Hub and other
tailnet clients. The HTTPS ingress route uses Traefik's cluster TLS handling
unless a real certificate is configured later, so command-line smoke tests use
`curl -k`. Protected API calls still require
`Authorization: Bearer <ope-api-key>`.

## To-do before real deployment

- Create provider environment values as GitHub Actions secrets, not repo files.
- Create `OPE_API_KEYS` as a GitHub Actions secret.
- Create Kubernetes secrets from the workflow at deploy time.
- Replace the sslip.io staging host with a real DNS name and certificate.
- Decide whether O.P.E. should use the existing Octo MinIO for artifacts/log bundles.
