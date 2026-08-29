# Phase 2A AWS infrastructure

This directory defines the smallest approved AWS platform for the existing
containerized FastAPI service. It now declares a partial S3 backend for future
Phase 3C delivery, but the current destroyed/empty local state has not been
migrated and the backend bucket has not been created.

## Lifecycle status

The Phase 2 environment completed this temporary lifecycle:

```text
Provisioned -> Deployed -> Validated -> Intentionally destroyed
```

The environment is currently offline and has no live endpoint. Destruction was
deliberate, occurred after evidence capture, and was part of cost control and
infrastructure-lifecycle validation. Exact lifecycle timestamps and any
unrecorded item-level checks are identified in the sanitized
[Phase 2 evidence](../evidence/phase2-aws-deployment-and-cleanup.md).

| Recorded event | Result |
| --- | --- |
| Bootstrap apply started | `2026-08-26 20:31:02 UTC` |
| Application validation | Evidence window `2026-08-26 23:42:00 UTC` through `2026-08-26 23:43:02 UTC` |
| Cleanup started | `2026-08-26 23:56:47 UTC` |
| Terraform destruction result | `0 added, 0 changed, 32 destroyed`; exact completion timestamp not recorded |

Before destruction, the ECS service was active at desired/running/pending
counts `1/1/0`, its rollout was complete, the Fargate task was running and
healthy, the ALB target was healthy, repeated health requests returned HTTP
`200`, and CloudWatch application logging was confirmed.

## Architecture

The VPC spans two availability zones. Each zone contains one public and one
private subnet. An internet-facing Application Load Balancer occupies both
public subnets and forwards HTTP port 80 to ECS Fargate task IPs on port 8080.
The ECS service can place Fargate tasks in either private subnet, and tasks do
not receive public IP addresses. A `desired_count` of `1` does not guarantee
simultaneous task placement across both availability zones.

Both private subnets share one route through a NAT Gateway in public subnet A.
The NAT path lets a task pull its ECR image and publish logs over HTTPS without
accepting internet-initiated traffic.

```text
Internet
   |
   v
ALB in public subnets :80
   |
   v
Fargate task ENIs in private subnets :8080
   |
   v
Single NAT Gateway -> Internet Gateway -> AWS public APIs
```

## Resource purpose

- The VPC, four subnets, internet gateway, route tables, routes, and
  associations establish the public and private network tiers.
- One EIP and NAT Gateway provide private-task outbound IPv4 connectivity.
- Separate ALB and ECS security groups constrain the only permitted traffic
  path: client TCP/80 to ALB, ALB TCP/8080 to ECS, and ECS TCP/443 outbound.
- ECR stores immutable application images and scans each pushed image.
- The ECS cluster, task definition, and service run the Linux/X86_64 workload
  on Fargate.
- The execution role lets the Fargate agent pull only this repository's image
  and write only this application's log streams. The application has no task
  role because it calls no AWS APIs.
- The CloudWatch log group retains application logs for seven days.

No database, HTTPS certificate, domain, WAF, autoscaling, service discovery,
secrets, ECS Exec, VPC endpoint, flow log, or alarm is created by this root.
The remote-state bucket and delivery identity belong to the separate retained
`bootstrap/` root.

## Inputs

All inputs have assessment-safe defaults. Important inputs are:

| Name | Default | Purpose |
| --- | --- | --- |
| `aws_region` | `eu-central-1` | Approved deployment region |
| `availability_zones` | `eu-central-1a`, `eu-central-1b` | Subnet placement |
| `allowed_http_cidrs` | `0.0.0.0/0` | Sources allowed to use HTTP/80 |
| `image_tag` | Required | Full lowercase 40-character Git SHA used by the task definition |
| `desired_count` | `0` | Task count before the first image push |
| `additional_tags` | `{}` | Extra non-sensitive resource tags |

The VPC and subnet CIDRs, port 8080, task size, health path, and log retention
are also variables, but validation pins them to the approved design.

`image_tag` is required even when `desired_count = 0`; `bootstrap`, `latest`,
branch names, and short SHAs are rejected. Never put credentials, tokens,
account identifiers, or sensitive application values in variable files.

## Outputs

Terraform returns the region, VPC and subnet IDs, ECR repository name and URL,
ECS cluster and service names, current task-definition ARN, CloudWatch log-group
name, ALB DNS name, and temporary HTTP application URL. Account-derived URLs,
ARNs, DNS names, URLs, and resource IDs are marked sensitive. This suppresses
ordinary display but does not remove those values from Terraform state;
workflows must not run unfiltered `terraform output` or publish state/plans.

## Local validation

Offline initialization downloads the provider and creates `.terraform.lock.hcl`;
it does not create AWS resources or configure the declared backend. The lock
file should be committed, while the `.terraform` directory must remain ignored.

```bash
terraform fmt -recursive infra
terraform fmt -check -recursive infra
terraform -chdir=infra init -backend=false -input=false -reconfigure
terraform -chdir=infra validate -no-color
trivy config --misconfig-scanners terraform --skip-check-update \
  --severity HIGH,CRITICAL --exit-code 1 --quiet infra
trivy filesystem --scanners secret --severity HIGH,CRITICAL \
  --exit-code 1 --no-progress infra
```

The approved assessment design intentionally produces these Trivy findings;
they remain visible and are not placed in an ignore file:

- `AWS-0053` (High): the ALB must be public for the temporary endpoint.
- `AWS-0054` (Critical): TLS, ACM, and a domain are deferred, so the temporary
  listener must use plaintext HTTP.
- `AWS-0104` (Critical): task egress permits HTTPS to public AWS endpoints
  through the NAT Gateway because VPC endpoints are explicitly out of scope.
- `AWS-0178` (Medium): VPC Flow Logs are explicitly out of scope.
- `AWS-0033` and `AWS-0017` (Low): ECR and CloudWatch Logs use AWS-managed
  encryption instead of additional customer-managed KMS keys.
- `AWS-0034` (Low): Container Insights is explicitly disabled.

Consequently, a High/Critical blocking scan exits `1` until the later HTTPS
and private-endpoint work removes the relevant exceptions. This is an accepted
assessment result, not a claim that the scan is clean.

Authenticate to AWS before running Terraform plan or apply commands:

```bash
aws login --remote --profile assessment-admin --region eu-central-1
export AWS_PROFILE=assessment-admin
export AWS_REGION=eu-central-1
export AWS_DEFAULT_REGION=eu-central-1
eval "$(aws configure export-credentials --profile assessment-admin --format env)"
```

These credentials are temporary, must never be committed, and may need to be
renewed when they expire.

A plan is read-only with respect to AWS resources, but it queries the selected
account and may contain account metadata. Do not save plan files in Git.

```bash
AWS_PROFILE=assessment-admin terraform -chdir=infra plan \
  -var='desired_count=0'
```

## Image deployment

1. Select the exact full Git commit SHA and apply the infrastructure with that
   `image_tag` and `desired_count = 0`. The ALB has no healthy targets at this
   stage, so an HTTP 503 is expected.
2. Read `ecr_repository_url` from the Terraform outputs.
3. Build and validate the application image for `linux/amd64`.
4. Authenticate to ECR, tag the image with a unique Git commit identifier, and
   push it. Do not use `latest`, and do not reuse an immutable tag.
5. Keep `image_tag` set to that exact full SHA and change `desired_count` to `1`.
6. Apply again, wait for the ECS deployment and ALB target to become healthy,
   then verify `/health` through `application_url`.

Changing the image tag creates a new task-definition revision. The deployment
circuit breaker stops and rolls back failed deployments. The first live
deployment has no known-good running revision, so rollback becomes genuinely
useful only after that deployment completes successfully.

## Apply and cleanup commands

The commands below are not ready for use until the separate bootstrap has been
applied and the local application state has passed the documented manual remote
state migration checkpoint. The implemented but unexecuted workflows will
supply the private bucket name through a temporary `.tfbackend` file under
`${RUNNER_TEMP}`. See the
[Phase 3C design](../docs/phase3c-continuous-delivery.md). State, backend files,
and plans must never be public artifacts.

These commands document the workflow for a future deliberate recreation.
Review a fresh plan before every apply; do not reuse a stale saved plan:

```bash
AWS_PROFILE=assessment-admin terraform -chdir=infra plan
AWS_PROFILE=assessment-admin terraform -chdir=infra apply
```

After validation and evidence capture, review cleanup and destroy the temporary
environment deliberately:

```bash
AWS_PROFILE=assessment-admin terraform -chdir=infra destroy
```

The ECR repository uses `force_delete = true` because it is a disposable,
project-named assessment repository. The protected destroy workflow first scales
ECS to zero, validates a deletion-only saved plan, and applies that exact plan;
Terraform then owns repository and image cleanup as one reviewed operation. A
production repository with retention or forensic requirements should use a
separately approved image-retention policy instead.

## Limitations and tradeoffs

- The partial S3 backend is not operational until bootstrap and the separate
  manual migration checkpoint complete. Until then, the ignored local state
  remains the authoritative state and must be privately backed up.
- S3 native lock files and GitHub concurrency will provide separate protection:
  the former protects state operations, while the latter serializes workflow
  scheduling. S3 versioning is the planned state recovery mechanism.
- The NAT Gateway, ALB, public IPv4 addresses, running Fargate task, ECR image
  storage, CloudWatch log ingestion/storage, and data transfer can incur cost.
  NAT and ALB hourly charges begin even while the service desired count is zero.
- A single NAT Gateway reduces assessment cost but makes outbound startup and
  logging from both zones dependent on one zone. Traffic from private subnet B
  to NAT Gateway A can also incur cross-zone data-transfer charges.
- The public listener is plaintext HTTP and defaults to all IPv4 sources. It is
  suitable only for a temporary non-sensitive assessment endpoint.
- AWS Fargate does not support ECS `dockerSecurityOptions`, so Docker's
  `no-new-privileges` setting cannot be reproduced. The task still runs as
  `10001:10001`, uses a read-only root filesystem, and drops all Linux
  capabilities. These controls mitigate risk but are not semantic equivalents.
- Desired count zero verifies infrastructure shape but does not test image
  pulls, log delivery, container health, target registration, or application
  reachability.
