# Phase 3B Kubernetes CI validation

## Purpose

Phase 3B validates the Kubernetes reference configuration without creating or
contacting a Kubernetes cluster. The CI job renders the Kustomization, validates
the resulting Kubernetes schemas, and checks deterministic workload and
security policies before the image build and runtime job can start.

## Execution status

| Field | Recorded value |
| --- | --- |
| Run number | `#5` |
| Trigger | Push |
| Branch | `feature/assessment-implementation` |
| Workflow commit | `71ef21f1aaea0fdf253db0ca3f4d5b9a4364fcec` |
| Exact execution timestamp | `Not recorded` |
| Duration | `1 minute 10 seconds` |
| Result | `Success` |
| Workflow warnings | None reported |
| Node.js deprecation warnings | None reported |

All four workflow jobs completed successfully:

| Job | Result | Duration |
| --- | --- | --- |
| Quality, tests, and repository security | Success | 25 seconds |
| Terraform formatting and validation | Success | 17 seconds |
| Kubernetes rendering, schema, and policy validation | Success | 9 seconds |
| Build, scan, and hardened runtime test (Docker) | Success | 40 seconds |

The workflow produced one Docker build-record artifact. It was temporary build
metadata, not a published container image. Its artifact name and digest are
intentionally omitted from this sanitized record.

## Native rendering and schema validation

The Kubernetes job used native `kubectl kustomize k8s` rendering and saved the
result under the temporary GitHub-hosted runner directory. Rendering was local
to the runner and did not use or contact a Kubernetes API server.

The rendered output contained exactly these six resource kinds:

- `Namespace`
- `ServiceAccount`
- `Deployment`
- `Service`
- `NetworkPolicy`
- `PodDisruptionBudget`

Strict, versioned Kubeconform validation completed successfully. Missing or
invalid schemas were not suppressed.

## Offline policy assertions

The successful policy-validation step parsed every rendered YAML document with
safe loading and confirmed:

- The Deployment specifies exactly two replicas.
- The application container exposes port `8080`.
- Startup, readiness, and liveness probes use `/health`.
- The Pod runs as non-root UID/GID `10001:10001`.
- The Pod uses the `RuntimeDefault` seccomp profile.
- The container root filesystem is read-only.
- Privilege escalation is disabled and the container is non-privileged.
- Every Linux capability is dropped.
- Service-account token mounting is disabled on the ServiceAccount and Pod.
- CPU and memory requests and limits are present.
- The Service is `ClusterIP` only.
- No Ingress, LoadBalancer, or NodePort is present.
- NetworkPolicy applies both ingress and egress isolation.
- The PodDisruptionBudget specifies `minAvailable: 1`.
- No workload image uses the `latest` tag.
- The deliberately invalid registry and `REPLACE_WITH_GIT_SHA` image
  replacement placeholder remain present.

These checks were cluster-offline configuration validation. No Kubernetes
context or API server was accessed.

## Deployment safety and boundaries

The reference image remains:

```text
registry.example.invalid/platform-assessment:REPLACE_WITH_GIT_SHA
```

The non-resolving registry and replacement placeholder deliberately prevent an
accidental successful deployment. An operator must explicitly substitute an
approved registry and immutable tested image identifier before deployment.

The manifests remain undeployed and have not been tested for:

- Admission by a real Kubernetes cluster
- CNI NetworkPolicy enforcement
- Pod scheduling or placement
- Rolling-update behavior
- Pod disruption behavior
- Registry authentication
- Pulling a real application image

No Kubernetes cluster was created, accessed, or modified. No workload was
deployed, and no public Kubernetes endpoint exists. The workflow did not access
AWS, authenticate to a registry, publish an image, or perform a cloud
deployment. Continuous delivery, registry publishing, and live cloud
deployment remain pending.

## Sanitization

This record excludes account IDs, ARNs, real-account registry URLs,
credentials, tokens, GitHub run URLs, Kubernetes contexts, cluster endpoints,
and raw logs containing identifiers. The documented `.invalid` registry is an
intentional non-resolving placeholder, not a real registry or sensitive value.
