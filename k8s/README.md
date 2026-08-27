# Kubernetes reference deployment

## Purpose and scope

These manifests provide a secure Kubernetes reference deployment for the
`platform-assessment` health service. They are configuration and documentation
only: native Kustomize rendering, strict schema validation, and deterministic
policy assertions passed in GitHub Actions without workflow warnings. They have
not been admitted or applied to a Kubernetes cluster and create no Ingress,
LoadBalancer, NodePort, or other public endpoint. See the sanitized
[Phase 3B Kubernetes CI evidence](../evidence/phase3b-kubernetes-ci-validation.md).
Continuous delivery, registry publishing, and live deployment remain pending.

## Files

- `namespace.yaml` creates the dedicated namespace and requests the restricted
  Pod Security Admission profile.
- `service-account.yaml` creates the workload identity without API permissions
  or automatic token mounting.
- `deployment.yaml` defines two hardened replicas, health probes, resources,
  rolling updates, and soft node spreading.
- `service.yaml` exposes the Pods only through an internal ClusterIP Service.
- `network-policy.yaml` limits application ingress and denies all egress.
- `pod-disruption-budget.yaml` preserves one available replica during voluntary
  disruptions.
- `kustomization.yaml` renders the resources in deterministic order and defines
  the image replacement point.

## Security controls

The namespace uses `restricted` for the Pod Security Admission `enforce`,
`audit`, and `warn` modes. Their version is `latest` for portability across
clusters that support admission labels. This adopts the profile supplied by the
target cluster, so the manifests must be retested during cluster upgrades. A
production environment can instead pin the version labels to its tested
Kubernetes minor version and use `latest` for audit and warning visibility.

The Deployment uses the dedicated service account and disables automatic token
mounting on both the ServiceAccount and Pod. No Role or RoleBinding exists
because the application does not call the Kubernetes API. The Pod runs as
UID/GID `10001:10001`, requires a non-root identity, and uses the runtime-default
seccomp profile. The container prevents privilege escalation, is explicitly
non-privileged, uses a read-only root filesystem, and drops every Linux
capability without adding any. No `fsGroup` is required because there are no
volumes, and no writable `emptyDir` or temporary filesystem is added.

## Image immutability and replacement

The reference image is:

```text
registry.example.invalid/platform-assessment:REPLACE_WITH_GIT_SHA
```

The registry is intentionally invalid, and the tag is a syntactically valid
non-production placeholder. Applying it unchanged will produce an image-pull
failure. Before any deployment, edit the `images` entry in
`kustomization.yaml`: replace `newName` with the approved registry/repository
and replace `newTag` with the full immutable Git commit SHA associated with the
tested image. Do not use `latest` or a mutable environment tag.

`imagePullPolicy: IfNotPresent` is appropriate only because the replacement tag
is required to be immutable. Registry publishing and credential design are
outside this reference configuration.

## Rendering and CI validation

From the repository root, render with either installed implementation:

```bash
kubectl kustomize k8s
kustomize build k8s
```

Only one command is necessary. `kubectl kustomize` and `kustomize build` render
locally and do not require a cluster.

The Phase 3B GitHub Actions job successfully used native Kustomize rendering,
strict versioned Kubeconform schema validation, and safe YAML policy assertions.
It confirmed exactly one Namespace, ServiceAccount, Deployment, Service,
NetworkPolicy, and PodDisruptionBudget, along with the documented replica,
health-probe, non-root, seccomp, filesystem, privilege, capability, token,
resource, network-isolation, disruption-budget, and image-placeholder policies.
The four-job workflow completed without workflow or Node.js deprecation
warnings.

This was cluster-offline configuration validation: it did not use a Kubernetes
context or contact a Kubernetes API server. Admission and API-version
compatibility with a specific target cluster remain unverified.

Some `kubectl` client-side dry-run paths still perform API discovery. Do not use
an active context for offline review. For guaranteed offline schema validation,
use a pinned validator and a locally provisioned schema bundle appropriate to
the target Kubernetes version.

## Deployment instructions

The commands in this and the following sections contact and modify the selected
cluster. They are operator guidance only and were not run for this assessment.
First replace the intentionally invalid image and inspect the rendered output.
Then, with an explicitly verified context, apply the Kustomization:

```bash
kubectl config current-context
kubectl apply -k k8s
```

No image pull secret is included. Configure registry access separately using
the target platform's approved identity mechanism if the chosen registry is
private.

## Rollout verification

```bash
kubectl --namespace platform-assessment rollout status \
  deployment/platform-assessment --timeout=5m
kubectl --namespace platform-assessment get pods \
  --selector app.kubernetes.io/name=platform-assessment
kubectl --namespace platform-assessment get service platform-assessment
```

Two desired replicas, soft topology spreading, and a disruption budget improve
availability but do not guarantee it. The scheduler prefers different nodes and
can place both replicas together when necessary. The budget protects against
voluntary disruptions only, not node loss or other involuntary failures.

## Health verification

The startup probe allows up to approximately 60 seconds for startup. Readiness
is checked every 5 seconds. Liveness is checked every 15 seconds and requires
four consecutive failures before restart, avoiding an aggressive restart loop.
All probes use HTTP `GET /health` through the named `http` port.

For temporary operator-only verification, forward the ClusterIP Service to
loopback in one terminal:

```bash
kubectl --namespace platform-assessment port-forward \
  service/platform-assessment 8080:80
```

Then verify the health contract from another terminal:

```bash
curl --fail --silent --show-error http://127.0.0.1:8080/health
```

The expected response is `{"status":"healthy"}`. Stop port forwarding after
verification.

## NetworkPolicy client access

The NetworkPolicy selects only the application Pods. It denies unsolicited
ingress except TCP port `8080` from Pods in the same namespace carrying this
label:

```yaml
platform-assessment-access: "true"
```

The policy denies all egress because the current application has no external
dependencies and does not require DNS. If DNS, telemetry, or another dependency
is added, allow only its required destinations and ports. NetworkPolicy has no
effect unless the target cluster's CNI enforces it.

## Cleanup

After explicitly verifying the context, remove these resources with:

```bash
kubectl delete -k k8s
```

This also requests deletion of the dedicated namespace and everything remaining
inside it. Review namespace contents and retention requirements before cleanup.

## Assumptions

- The target cluster supports the stable `apps/v1`, `networking.k8s.io/v1`, and
  `policy/v1` APIs and Kustomize `v1beta1` configuration.
- Nodes provide the standard `kubernetes.io/hostname` label.
- The approved image preserves the tested non-root UID/GID, port, health path,
  and read-only-filesystem compatibility.
- Any selected private registry access is configured outside these manifests.
- The cluster operator verifies the context and rendered diff before applying.

## Known limitations

- The manifests have not been deployed or admitted by a real cluster.
- Scheduling, rolling updates, Pod disruption behavior, registry
  authentication, and real image pulling have not been tested.
- The example registry is intentionally invalid and cannot pull an image.
- No public endpoint is created.
- Pod Security Admission depends on cluster version and configuration.
- NetworkPolicy structure passed CI policy and schema checks, but enforcement
  has not been tested with a real CNI implementation.
- CPU and memory settings are assessment defaults, not measured production
  capacity.
- The process-only health endpoint does not validate external dependencies.

## Production enhancements

- Maintain the pinned CI rendering and schema-validation toolchain as supported
  Kubernetes versions change.
- Test admission, rollout, disruption, and network isolation on a disposable
  cluster before promotion.
- Add TLS and an authenticated Ingress or Gateway only when public exposure is
  required.
- Add measured resource sizing and horizontal autoscaling.
- Add monitoring, alerting, and centralized log collection.
- Add a secrets-management integration if the application gains secrets.
- Pin image identity by digest in addition to retaining the Git-SHA tag.
