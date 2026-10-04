#!/usr/bin/env bash
# Select existing cluster access without changing kubeconfig permissions.
set -euo pipefail
: "${KUBECONFIG:?KUBECONFIG is required}"
: "${RUNNER_TEMP:?RUNNER_TEMP is required}"
: "${GITHUB_ENV:?GITHUB_ENV is required}"

if command -v kubectl >/dev/null; then
  client=("$(command -v kubectl)")
elif command -v k3s >/dev/null; then
  client=("$(command -v k3s)" kubectl)
else
  echo "::error::No kubectl/k3s on this runner."
  exit 1
fi

prefix=()
if ! "${client[@]}" --kubeconfig="$KUBECONFIG" --request-timeout=10s version --output=yaml >/dev/null 2>&1; then
  # Some control-plane runners have pre-existing passwordless sudo for k3s.
  # Reuse it only if the same bounded cluster probe succeeds; never grant sudo,
  # copy credentials, or relax file permissions as part of deployment.
  if command -v sudo >/dev/null && sudo -n -- "${client[@]}" --kubeconfig="$KUBECONFIG" --request-timeout=10s version --output=yaml >/dev/null 2>&1; then
    prefix=("$(command -v sudo)" -n --)
    echo "Using the runner's existing noninteractive sudo access for kubectl."
  else
    echo "::error::Runner cannot reach the cluster with KUBECONFIG=$KUBECONFIG, directly or through existing noninteractive sudo. Configure the runner's authorized Kubernetes access."
    exit 1
  fi
fi

wrapper="$RUNNER_TEMP/ope-kubectl"
{
  printf '#!/usr/bin/env bash\nexec '
  printf '%q ' "${prefix[@]}" "${client[@]}" "--kubeconfig=$KUBECONFIG"
  printf '"$@"\n'
} > "$wrapper"
chmod 700 "$wrapper"
printf 'KUBECTL=%s\n' "$wrapper" >> "$GITHUB_ENV"
