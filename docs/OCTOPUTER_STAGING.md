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

```bash
kubectl apply -f k8s/postgres.yaml
kubectl apply -f k8s/redis.yaml
kubectl apply -f k8s/litellm.yaml
kubectl apply -f k8s/ope-core.yaml
```

## To-do before real deployment

- Add a GitHub Actions workflow like `Octo — Deploy OPE`.
- Pin it to `vars.OCTO_CP_RUNNER || '["self-hosted","octo-cp"]'`.
- Create provider environment values as GitHub Actions secrets, not repo files.
- Create Kubernetes secrets from the workflow at deploy time.
- Add an ingress or NodePort only after the internal service works.
- Decide whether O.P.E. should use the existing Octo MinIO for artifacts/log bundles.
