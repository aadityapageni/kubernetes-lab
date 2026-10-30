#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 || ! "$1" =~ ^[a-z0-9][a-z0-9._/-]*@sha256:[a-f0-9]{64}$ ]]; then
  echo "Usage: $0 registry/image@sha256:<64 hex characters>" >&2
  exit 2
fi

image_name="${1%@*}"
image_digest="${1#*@}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
overlay="$(mktemp -d "$repo_root/.release.XXXXXXXX")"
trap 'rm -f "$overlay/kustomization.yaml"; rmdir "$overlay"' EXIT

cat > "$overlay/kustomization.yaml" <<EOF
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - ../k8s
images:
  - name: otel-shop
    newName: $image_name
    digest: $image_digest
EOF

kubectl apply -f "$repo_root/k8s/00-namespace.yaml"
kubectl apply -k "$overlay"
for deployment in jaeger otel-collector frontend checkout inventory payment; do
  kubectl rollout status "deployment/$deployment" -n observability --timeout=180s
done
kubectl get deployments -n observability
