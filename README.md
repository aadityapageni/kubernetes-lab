# Kubernetes Platform Lab: Shop + OpenTelemetry

A four-service FastAPI demo for Kubernetes and DevOps practice. Requests follow `frontend → checkout → inventory + payment`; an OpenTelemetry Collector exports spans to Jaeger. The app also exposes Prometheus metrics. The repository includes tests, a container build, Kubernetes manifests, optional platform exercises, and a GitHub Actions CI/CD workflow.

Use the [8-area, 24-concept guide](docs/KUBERNETES_UNIVERSE.md) to work through the supplied Kubernetes image. Optional exercises cover configuration, Ingress, storage, autoscaling, RBAC, Trivy, Falco, Prometheus, and Grafana. Cluster-level tools have separate prerequisites and are not installed by the default app release.

## Quick start

Prerequisites: Python 3.12, Docker or Podman, a Kubernetes cluster, and `kubectl` with access to that cluster.

```bash
python3.12 -m venv .venv
. .venv/bin/activate
pip install -r app/requirements-dev.txt
PYTHONPATH=app pytest -q app/tests
ruff check app
kubectl kustomize k8s > /tmp/otel-rendered.yaml
python scripts/check_manifests.py
```

Build and publish the image to a registry the cluster can pull from:

```bash
podman build -t registry.example.com/otel-shop:1.0.0 app
podman push registry.example.com/otel-shop:1.0.0
```

Resolve the pushed image digest, then deploy the immutable image reference:

```bash
bash scripts/deploy.sh 'registry.example.com/otel-shop@sha256:<64-character-digest>'
```

The deployment script applies the namespace and manifests, then waits for all six deployments. It does not install cluster infrastructure. The Cilium address pool and local-path provisioner manifests at the repository root are optional, cluster-specific examples.

## CI/CD

Pull requests run dependency resolution, Ruff, tests, manifest rendering, optional lab validation, a Trivy configuration scan, and a container build. Pushes to `main` and manual dispatches also publish the image to GHCR with a commit SHA tag and scan it with Trivy. Deployment runs only when the repository variable `DEPLOY_ENABLED` is `true` and the `production` environment has a `KUBECONFIG_B64` secret. The deployment uses the pushed image digest. See [operations guide](docs/OPERATIONS.md) for setup, rollback, security boundaries, and troubleshooting.

## Generate traces

```bash
kubectl port-forward -n observability svc/frontend 8080:8080
curl http://localhost:8080/
curl -i 'http://localhost:8080/?fail=payment'
curl 'http://localhost:8080/?slow=payment'
```

In another terminal:

```bash
kubectl port-forward -n observability svc/jaeger 16686:16686
```

Open <http://localhost:16686>, select `frontend`, and search for traces. The failure request returns an error; the slow request adds about 1.5 seconds to payment.

## Scope

This is a deployable lab, not a production observability backend. Jaeger uses memory storage, so traces vanish on restart. For a production system, choose durable supported storage, retention, authentication and TLS, backup, and a highly available backend before exposing it to users.
