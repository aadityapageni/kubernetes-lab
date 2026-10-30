# CI/CD and deployment operations

## Pipeline contract

| Event | Verify | Build | Publish | Deploy |
| --- | --- | --- | --- | --- |
| Pull request | Yes | Yes | No | No |
| Push to `main` | Yes | Yes | Yes | If enabled |
| Manual dispatch | Yes | Yes | Yes | If enabled and run on `main` |

`verify` runs `pip check`, Ruff, pytest, `kubectl kustomize`, optional lab YAML validation, and a Trivy configuration scan. `image` builds the single container used by all four app roles, pushes a `sha-<commit>` tag to GHCR, and scans that image. Trivy findings are informational until the baseline is triaged. `deploy` applies that image by digest, waits for Jaeger, Collector, and each app rollout, then calls the frontend through a port-forward as a smoke test. Deployment is serialized per Git ref. Dependabot opens weekly update PRs for actions, Python packages, and the base image.

## Configure GitHub deployment

1. Push this repository to GitHub and protect `main` with the `verify` and `image` checks.
2. Create a `production` environment. Add reviewers if deployment requires approval.
3. Create the repository variable `DEPLOY_ENABLED` with value `true`.
4. Add a `KUBECONFIG_B64` secret to the `production` environment. Encode a dedicated Kubernetes deploy identity's kubeconfig using `base64 -w0 ~/.kube/config` on Linux. Grant only the access needed for the namespace and resources in `k8s/`; initial namespace creation requires cluster-level permission. Do not commit the kubeconfig.
5. Ensure the runner can reach the Kubernetes API. A private cluster needs a network-connected self-hosted runner; change `runs-on` for the deploy job accordingly.
6. Ensure cluster nodes can pull the GHCR image. Make the package public or configure an `imagePullSecret` for private packages and attach it to the app pod templates.

Keep `DEPLOY_ENABLED` unset until these requirements are in place. The GHCR image name is `ghcr.io/<owner>/<repo>` in lowercase. A manual dispatch publishes the selected commit, but only `main` may deploy.

## Deploy from another CI system

The GitHub workflow is optional. Any CI system can run these commands after supplying Python, a container builder, `kubectl`, registry credentials, and cluster credentials:

```bash
python -m pip install -r app/requirements-dev.txt
python -m pip check
ruff check app
PYTHONPATH=app pytest -q app/tests
kubectl kustomize k8s > /tmp/otel-rendered.yaml
docker build -t "$IMAGE_TAG" app
docker push "$IMAGE_TAG"
bash scripts/deploy.sh "$IMAGE_WITH_DIGEST"
```

`IMAGE_WITH_DIGEST` must be a pullable reference of the form `registry/image@sha256:<64 hex characters>`. Publish before deploying; a tag alone is not accepted. The deploy script needs Kubernetes access through the usual `KUBECONFIG` or in-cluster configuration.

## Verify and rollback

```bash
kubectl get deployments,pods,svc -n observability
kubectl rollout status deployment/frontend -n observability
kubectl logs deployment/otel-collector -n observability
kubectl port-forward -n observability svc/frontend 8080:8080
curl -fsS http://localhost:8080/healthz
curl -fsS http://localhost:8080/readyz
```

To roll back all four app services, deploy the previous published digest with `bash scripts/deploy.sh <previous-image@sha256:digest>`. If a deployment fails during rollout, inspect `kubectl describe pod -n observability -l app=frontend` and the deployment's logs. The script exits nonzero on rollout failure; it does not auto-rollback.

## Operational limits

- Jaeger stores traces in memory. A restart loses data; one Jaeger replica is intentional for the lab.
- The collector and Jaeger endpoints use plaintext inside the cluster. Do not expose them or the Jaeger UI publicly without access control and TLS.
- `always_on` tracing is suitable for demos. Adjust sampling and resource limits for real traffic.
- The root-level Cilium and local-path manifests are not in the release pipeline. Install them only when appropriate for the cluster.
- Python dependencies have bounded version ranges rather than a lock file. For strictly reproducible releases, add and maintain a hash-pinned lock and rebuild after dependency updates.
