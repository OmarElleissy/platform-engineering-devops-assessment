# Phase 2 AWS Deployment and Cleanup Evidence

## Scope

This sanitized record documents the reported Phase 2 lifecycle, the verified
container vulnerability remediation, the troubleshooting decisions, and the
intentional destruction of the temporary AWS environment. It does not contain
raw command output or environment-specific identifiers.

The available record supports the overall lifecycle outcome. Where exact
timestamps, counts, or item-level verification output were not retained, this
document says `TBD` or `Not recorded` rather than inferring a result.

## Final lifecycle status

```text
Provisioned -> Deployed -> Validated -> Intentionally destroyed
```

| Stage | Recorded status | Evidence boundary |
| --- | --- | --- |
| Provisioned | Completed | Bootstrap apply began at `2026-08-26 20:31:02 UTC` and the expected infrastructure began creating; the completion timestamp and apply summary were not retained. |
| Deployed | Completed | The application was reported deployed to ECS Fargate; the deployed Git image tag was not retained in the available sanitized record. |
| Validated | Completed | ECS, task, ALB, endpoint, repeated-request, and CloudWatch evidence was recorded between `2026-08-26 23:42:00 UTC` and `2026-08-26 23:43:02 UTC`. |
| Intentionally destroyed | Completed | Cleanup began at `2026-08-26 23:56:47 UTC`; Terraform later reported `0 added, 0 changed, 32 destroyed`. The exact completion timestamp and independent post-destroy checks were not retained. |

There is currently no live endpoint. Destruction was part of both cost control
and infrastructure-lifecycle validation, not an outage or unresolved defect.

## Deployment timeline

| Event | Recorded time or result |
| --- | --- |
| Bootstrap apply started | `2026-08-26 20:31:02 UTC` |
| Bootstrap apply completed | **Not recorded — completion timestamp and apply summary unavailable** |
| Image build, scan, and deployment | Completed during the lifecycle; exact deployed Git tag and event timestamps not recorded |
| Successful application validation | Evidence window from `2026-08-26 23:42:00 UTC` through `2026-08-26 23:43:02 UTC` |
| Validation evidence recorded through | `2026-08-26 23:43:02 UTC` — the last timestamp visible in the retained validation evidence |
| Cleanup initiated | `2026-08-26 23:56:47 UTC` |
| Terraform destruction result | `0 added, 0 changed, 32 destroyed` |
| Destruction completed | Successfully reported by Terraform; **exact completion timestamp not recorded** |

Bootstrap start, successful validation, and cleanup are distinct events. The
validation evidence is a window, not an invented single completion instant.
File modification times and Git commit times are not substitutes for the
missing bootstrap- and destruction-completion timestamps.

The recorded interval from bootstrap apply start to cleanup start was **3 hours,
25 minutes, 45 seconds**. This is the infrastructure lifecycle window up to the
beginning of cleanup, not an exact billable duration: destruction continued
after cleanup began, and AWS billing granularity may differ. Exact cost was not
recorded. The environment is intentionally offline.

## Application validation

| Check | Result |
| --- | --- |
| Bootstrap apply start | `2026-08-26 20:31:02 UTC`; expected infrastructure creation began |
| Bootstrap apply completion timestamp and resource summary | Not recorded |
| Deployed immutable Git image tag | Not recorded |
| ECS service status | `ACTIVE` |
| ECS desired, running, and pending counts | `1`, `1`, and `0` respectively |
| ECS deployment rollout | `COMPLETED` |
| ECS task status and health | `RUNNING` and `HEALTHY` |
| ECS launch type and platform | `FARGATE`, platform `1.4.0` |
| ECS task size | CPU `256`; memory `512 MiB` |
| ALB target | Port `8080`; state `healthy`; no failure reason reported |
| `/health` HTTP status | `200` |
| `/health` response body | `{"status":"healthy"}` |
| Repeated-request validation | Five consecutive additional health requests returned HTTP `200` |

The retained validation evidence spans `2026-08-26 23:42:00 UTC` through
`2026-08-26 23:43:02 UTC`. The latter is the last visible timestamp, not a
reconstructed validation-completion instant.

## Container security validation

The remediated image was rebuilt for Linux/X86_64 without relying on an old
build cache and tested under the existing hardened runtime controls:

| Control | Recorded result |
| --- | --- |
| Runtime identity | Non-root UID/GID `10001:10001` verified |
| Root filesystem | Read-only behavior verified |
| Linux capabilities | All capabilities dropped |
| Privilege escalation control | `no-new-privileges` used in local runtime validation; ECS Fargate does not expose an equivalent supported task option |
| Writable temporary filesystem | No writable tmpfs used in the remediation test |
| Container health | Docker health became healthy in the remediation test |

These are container-image and local hardened-runtime results. They do not by
themselves prove the separate ECS task-health or ALB target-health checks.

## Vulnerability remediation

The initial release-image scan found two **High** affected-package findings:

| Item | Recorded result |
| --- | --- |
| CVE | `CVE-2026-14456` |
| Affected packages | `libcrypto3` and `libssl3` |
| Installed vulnerable version | `3.5.7-r0` |
| Fixed version identified by the scanner | `3.5.8-r0` |
| Initial Python dependency findings | Zero |

This was one CVE affecting two Alpine packages, not two unrelated
vulnerabilities. The vulnerable image was not intentionally deployed.

The Dockerfile performs a targeted package update rather than a complete Alpine
upgrade:

```dockerfile
RUN apk add --upgrade --no-cache \
    'libcrypto3>=3.5.8-r0' \
    'libssl3>=3.5.8-r0'
```

The image was rebuilt with a fresh base lookup and no build cache, tested under
the hardened runtime controls, and rescanned. The recorded blocking result for
the exact remediated image was:

| Severity | Final total |
| --- | ---: |
| High | 0 |
| Critical | 0 |

No Trivy ignore rule, `--ignore-unfixed`, or other vulnerability suppression
was used. No fixable finding was accepted merely to pass the assessment.

This response demonstrates a blocking security gate, remediation rather than
suppression, source-to-image traceability, and a decision to resolve fixable
container findings before deployment. The exact deployed image tag is still
listed as `Not recorded`, so this document does not infer it from current Git
HEAD.

## Infrastructure validation

The bootstrap screenshot confirms Terraform began creating the expected
infrastructure at `2026-08-26 20:31:02 UTC`; it does not show the final apply
summary or exact completion time. Later evidence confirms the ECS service was
`ACTIVE`, its rollout was `COMPLETED`, desired/running/pending counts were
`1/1/0`, and the task was `RUNNING` and `HEALTHY` on Fargate platform `1.4.0`
with CPU `256` and memory `512 MiB`.

The ALB target was healthy on port `8080` with no failure reason. These results
were captured before intentional destruction. The architecture and Terraform
configuration remain reproducible from source.

## Observability validation

| Check | Result |
| --- | --- |
| Uvicorn server process | Startup recorded |
| Application startup | Completion recorded |
| Listening port | `8080` |
| Application health traffic | Multiple `GET /health` requests recorded with HTTP `200` |
| CloudWatch application logging | Confirmed |
| Validation log window | `2026-08-26 23:42:00 UTC` through `2026-08-26 23:43:02 UTC` |

During the failed `bootstrap` image attempt, CloudWatch application logs were
empty because the application image never started. That absence was a useful
diagnostic signal. After the correct image started, the retained evidence
confirmed the application logging path. Source addresses, source ports, and raw
log lines are intentionally omitted.

## Cleanup and destruction verification

Cleanup started at `2026-08-26 23:56:47 UTC`. Terraform subsequently reported
successful destruction with `0 added, 0 changed, 32 destroyed`; the exact
completion timestamp is not visible. Only the repository-emptying step and the
Terraform destruction result are supported by the retained evidence; the other
granular checks were not retained:

| Cleanup check | Result |
| --- | --- |
| ECS desired, running, and pending counts reached zero before destruction | Not recorded |
| ECR repository emptied before Terraform destruction | Confirmed — the dedicated repository was inventoried and its existing images were deliberately removed before repository destruction |
| Terraform applied the reviewed destruction plan | Destruction confirmed — `0 added, 0 changed, 32 destroyed`; separate evidence that the plan was reviewed was not recorded |
| Exact destruction-completion timestamp | Not recorded |
| ECR repository absent after destruction | Not recorded |
| ALB absent after destruction | Not recorded |
| ECS cluster inactive or absent | Not recorded |
| No active project NAT Gateway remained | Not recorded |
| No project Elastic IP remained allocated | Not recorded |
| Terraform state contained no managed resources | Not recorded |
| Temporary Terraform plan files removed | Not recorded |
| Docker logged out of ECR | Not recorded |
| Temporary AWS environment variables unset | Not recorded |

This distinction matters: Terraform's successful destruction summary is
recorded, while independent proof of the remaining post-destroy conditions is
absent.

## Reproducibility

The environment is intentionally offline but reproducible from committed
source. A future recreation should:

1. Authenticate with approved temporary AWS credentials immediately before the
   long-running workflow.
2. Initialize, format-check, validate, scan, and freshly plan Terraform.
3. Apply the zero-task bootstrap infrastructure.
4. Build and scan the exact committed Linux/X86_64 image without stale cache.
5. Push it under an immutable Git-SHA tag and verify that exact tag exists.
6. Update the ignored runtime variables with the verified tag.
7. Review a fresh plan, then scale the ECS service to one task.
8. Validate ECS status, task health, ALB target health, the health endpoint, and
   CloudWatch logs before collecting sanitized evidence.

Under normal AWS and network conditions, recreation is expected to take
approximately **15–25 minutes**. This is a documented estimate, not a measured
SLA or guaranteed recovery objective.

## Troubleshooting and lessons learned

| Incident | Cause or signal | Resolution | Preventive action |
| --- | --- | --- | --- |
| ECR push timeout | Docker timed out while completing a layer upload; already uploaded layers remained reusable, and an immediate retry did not resolve the path issue. | Docker upload concurrency was reduced to one. Authentication and image existence were verified after the push. | On unreliable or limited-bandwidth paths, lower upload concurrency and always verify the image exists before deployment. |
| Temporary credentials expired during Terraform waiting | Terraform submitted the ECS service update, then the short-lived token expired while Terraform waited for stabilization. The error did not prove a remote rollback. | Credentials were renewed, actual ECS state was inspected, and a fresh plan reconciled local and remote reality instead of blindly reapplying a stale saved plan. | Refresh temporary credentials immediately before long plans, applies, waiters, and destruction operations. |
| Incorrect `bootstrap` image reference | Scaling above zero still referenced the placeholder image, so ECS repeatedly reported `CannotPullContainerError`; application logs were empty because the image never started. | The runtime image tag was changed to the immutable Git-SHA tag that actually existed, followed by a new reviewed plan and apply. | Before scaling above zero, verify the exact tag exists and inspect the planned task-definition image reference. |
| Git HEAD and cleanup tag mismatch | Documentation commits moved HEAD after the deployed release was built, so current HEAD did not identify an image present in the dedicated repository. | Cleanup inventoried the repository and removed images by their actual identifiers before repository destruction; it did not guess or create another tag. | Retain the deployed release tag and digest as explicit sanitized evidence because Git HEAD can move. |
| ECR deletion dependency | `force_delete = false` prevented repository removal while images remained. | Images had to be removed deliberately before repository destruction. | Keep the safety control; make image inventory and authorized removal an explicit cleanup step. |

These incidents demonstrate diagnosis and reconciliation discipline. They are
not presented as unresolved defects.

## Known limitations and accepted tradeoffs

| Area | Assessment decision | Production enhancement |
| --- | --- | --- |
| Application availability | One ECS task demonstrated deployment but did not provide simultaneous multi-AZ capacity. | Run multiple tasks across failure domains with autoscaling and tested recovery objectives. |
| Outbound networking | One NAT Gateway reduced temporary cost and complexity but was a zonal dependency. | Evaluate one NAT per zone or private VPC endpoints. |
| Transport security | The assessment listener used plaintext HTTP with no retained custom domain. | Use ACM-managed TLS, HTTPS redirect, controlled DNS, and potentially WAF. |
| Terraform state | Local state was acceptable for a temporary single-operator assessment. | Use encrypted remote state with locking, versioning, backup, and controlled access. |
| Monitoring | CloudWatch Logs was configured, while advanced centralized monitoring was outside the minimal scope. | Add service metrics, alarms, flow logs, Container Insights, and centralized security monitoring. |
| Deployment automation | The workflow was deliberate and operator-driven. | Add gated CI/CD, artifact promotion, automated rollback tests, and verified cleanup automation. |
| Lifecycle | The environment was time-boxed and intentionally destroyed. | Define durable ownership, budgets, retention, incident response, and recovery procedures. |

This was a minimal demonstrable platform, not a claim of production readiness.
The accepted Terraform security-scan tradeoffs remain visible in
`infra/README.md`.

## Sanitization statement

This document intentionally omits AWS account IDs, ARNs, registry addresses,
repository URLs, task and request IDs, credentials, tokens, authentication
links, Terraform state content, load-balancer names, and public or internal IP
addresses. No live endpoint is published.
