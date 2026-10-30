# Kubernetes platform lab: 8 areas, 24 concepts

This repository is a small application for practicing the eight areas shown in the supplied image. The default release remains six Deployments: four shop services, an OpenTelemetry Collector, and Jaeger. Optional examples live under `labs/` and require the named cluster components. The application cannot install or replace Kubernetes control-plane components.

| Area | Concept | Where to practice it |
| --- | --- | --- |
| Control plane | API server | `kubectl get --raw /readyz` and `kubectl api-resources` |
| Control plane | etcd | Inspect control-plane health using your cluster provider; managed services may not expose etcd |
| Control plane | Scheduler | `kubectl describe pod -n observability -l app=frontend` for scheduling events |
| Workloads | Pod | `kubectl get pods -n observability -o wide` |
| Workloads | Deployment | `k8s/02-apps.yaml` and `kubectl rollout status deployment/frontend -n observability` |
| Workloads | Probes | `/healthz`, `/readyz`, and probes in `k8s/02-apps.yaml` |
| Config | ConfigMap | `k8s/01-config.yaml`; `GET /platform` displays `APP_MESSAGE` |
| Config | Secret | Optional `shop-secrets` key injected into payment without exposing its value |
| Config | Helm | Install the optional monitoring and Falco charts; see below |
| Networking | Service | Internal services in `k8s/01-jaeger.yaml` and `k8s/02-apps.yaml` |
| Networking | Ingress | `labs/networking/ingress.yaml`, requiring an Ingress controller |
| Networking | Cilium | `cilium-ip-pool.yaml`, only for a Cilium cluster with a suitable address range |
| Storage | PV | Dynamically provisioned when the optional claim binds |
| Storage | PVC | `labs/storage/claim-and-job.yaml` |
| Storage | StorageClass | Optional `local-path-storage.yaml`, or your cluster's own class |
| Scale and schedule | VPA | `labs/scaling/vpa.yaml`, recommendation-only; VPA must be installed |
| Scale and schedule | HPA | `labs/scaling/hpa.yaml`, requiring Metrics Server |
| Scale and schedule | Taints | Inspect node taints and pod scheduling; commands below |
| Security | Trivy | CI scans manifests and the published image, reporting high and critical findings |
| Security | Falco | Optional cluster-wide runtime detection installed with Helm |
| Security | RBAC | `labs/security/rbac.yaml` and `kubectl auth can-i` |
| Observability | Prometheus | `/metrics` on every app and optional `ServiceMonitor` |
| Observability | Grafana | Included in the optional kube-prometheus-stack Helm release |
| Observability | OpenTelemetry | SDK → Collector → Jaeger, in `app/main.py` and `k8s/01-jaeger.yaml` |

## Workloads and config

After deployment, inspect the workload and configuration:

```bash
kubectl get deploy,pods,svc,cm -n observability
kubectl describe deployment frontend -n observability
kubectl port-forward -n observability svc/frontend 8080:8080
curl http://localhost:8080/platform
curl http://localhost:8080/metrics
```

`shop-config` is applied by the default deployment. A ConfigMap update does not change environment variables in already-running Pods; restart the affected Deployments to use new values.

The payment service has an optional Secret reference. Create it only for the exercise:

```bash
kubectl create secret generic shop-secrets -n observability --from-literal=payment-demo-key='replace-with-a-demo-value'
kubectl rollout restart deployment/payment -n observability
kubectl port-forward -n observability svc/payment 8081:8080
curl http://localhost:8081/platform
```

The endpoint reports only whether the Secret is configured. It never returns the value. The app does not use this demo key for authentication or payment processing. For a real system, integrate a managed secret store and rotation policy.

## Networking

The base application uses ClusterIP Services. To try Ingress, first install an Ingress controller and confirm its class with `kubectl get ingressclass`. Then edit `ingressClassName` and `host` in `labs/networking/ingress.yaml` for your cluster and apply it:

```bash
kubectl apply -f labs/networking/ingress.yaml
kubectl describe ingress frontend -n observability
```

An Ingress resource alone does not provide routing. Add TLS and access control before exposing an endpoint publicly. `cilium-ip-pool.yaml` is a separate example of Cilium load-balancer address allocation; do not apply its private address range to an unrelated cluster.

## Storage

The storage example requires a `local-path` StorageClass. On a cluster with a different provisioner, change `storageClassName` in the claim. The root-level `local-path-storage.yaml` is a lab provisioner, not part of the app release.

```bash
kubectl apply -f labs/storage/claim-and-job.yaml
kubectl wait -n observability --for=condition=complete job/storage-demo --timeout=180s
kubectl get pvc -n observability
kubectl get pv
kubectl logs -n observability job/storage-demo
```

The PVC requests storage; the provisioner creates and binds a PV. Deleting the claim may delete its underlying volume according to the StorageClass reclaim policy. Use disposable data for this exercise.

## Scaling and scheduling

Install Metrics Server before the HPA exercise. The frontend has a CPU request, which the HPA uses for utilization calculations:

```bash
kubectl apply -f labs/scaling/hpa.yaml
kubectl get hpa -n observability
kubectl top pods -n observability
```

VPA is a separate cluster add-on. Once its CRD and controllers are installed, apply `labs/scaling/vpa.yaml` and inspect `kubectl describe vpa checkout-recommendations -n observability`. It uses `Off` mode, so it provides recommendations without changing Pods. It targets checkout rather than the HPA-managed frontend.

Taints are a node scheduling control. Inspect them with `kubectl describe nodes` and inspect Pod placement with `kubectl get pods -n observability -o wide`. In a disposable cluster, try tainting a non-control-plane node and observe Pending Pods, then remove the taint. Do not taint a shared or production node solely for this exercise.

## Security

The app Pods use a dedicated ServiceAccount without an API token, run as a non-root user, and drop Linux capabilities. To practice a narrowly scoped RBAC grant:

```bash
kubectl apply -f labs/security/rbac.yaml
kubectl auth can-i list pods -n observability --as=system:serviceaccount:observability:lab-reader
kubectl auth can-i get secrets -n observability --as=system:serviceaccount:observability:lab-reader
```

The first check should say `yes`; the second should say `no`. The CI workflow runs Trivy configuration and image scans. Findings are informational (`exit-code: 0`) until the team has triaged the baseline; make them a blocking gate when that baseline is clean.

Falco is a separate runtime security system and needs node-level access. On an appropriate Linux cluster:

```bash
helm repo add falcosecurity https://falcosecurity.github.io/charts
helm repo update
helm upgrade --install falco falcosecurity/falco -n falco --create-namespace
kubectl get pods -n falco
```

Review the Falco chart's privileges and driver requirements before installing it on a managed or shared cluster.

## Observability

OpenTelemetry traces flow through the Collector to Jaeger in the default release. The app also serves Prometheus metrics. For the optional Prometheus and Grafana stack, install the chart, then create the ServiceMonitor:

```bash
helm upgrade --install monitoring oci://ghcr.io/prometheus-community/charts/kube-prometheus-stack \
  -n monitoring --create-namespace -f labs/observability/monitoring-values.yaml
kubectl apply -f labs/observability/servicemonitor.yaml
kubectl get servicemonitor shop-apps -n observability
```

The values file enables discovery of ServiceMonitors in other namespaces. The ServiceMonitor selects the four app Services by label and scrapes `/metrics` on their named `http` port. Confirm targets in Prometheus before creating Grafana panels. The chart is sizeable; allow enough cluster resources. Jaeger is still in-memory and does not become durable by installing this chart.

## References

- [Kubernetes HPA walkthrough](https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale-walkthrough/)
- [Kubernetes Ingress prerequisites](https://kubernetes.io/docs/concepts/services-networking/ingress/)
- [Kubernetes dynamic volume provisioning](https://kubernetes.io/docs/concepts/storage/dynamic-provisioning/)
- [VPA quickstart](https://github.com/kubernetes/autoscaler/blob/master/vertical-pod-autoscaler/docs/quickstart.md)
- [Prometheus community chart](https://github.com/prometheus-community/helm-charts/tree/main/charts/kube-prometheus-stack)
- [Falco Kubernetes installation](https://falco.org/docs/setup/kubernetes/)
