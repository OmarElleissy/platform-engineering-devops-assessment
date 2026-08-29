# Phase 3C continuous-delivery design

## Final execution status

The manual, approval-gated deployment workflow completed successfully. It
published and deployed the immutable release to ECS Fargate, then verified a
stable service, exactly one running task, a healthy ALB target, HTTP `200`, and
the exact `{"status":"healthy"}` response.

Cleanup was a separate outcome. The automated destroy removed 31 of 32
Terraform-managed application resources and then failed on the final Elastic IP
disassociation. The historical destroy workflow was therefore not successful
or green. A separately reviewed saved Terraform plan containing exactly one
deletion removed `aws_eip.nat`. Final remote application state contains zero
managed and zero tainted resources, and independent project-scoped checks found
no remaining application resources.

The compact IAM resource-scope correction was subsequently applied. A fresh
bootstrap plan reported no changes, IAM simulation allowed disassociation for
both required resource types without missing context, and bootstrap remained at
nine managed and zero tainted resources. The encrypted, versioned, private S3
state bucket, GitHub OIDC provider, and lifecycle role remain intentionally
available for a future approved lifecycle.

## Scope and safeguards

Phase 3C separates ordinary CI from manual delivery to the assessment AWS
environment. The sections below document the implemented workflow behavior and
the operational lessons from its execution.

CI and CD are deliberately separate. Ordinary CI has only `contents: read`; it
tests application, Terraform, Kubernetes, workflow policy, and the exact local
image without AWS credentials. CD consists of two manual workflows protected by
the `assessment-aws` GitHub Environment:

- `Deploy application infrastructure`
- `Destroy application infrastructure`

Both require `main`, a typed confirmation, a protected-environment approval,
GitHub OIDC, and the same queued concurrency group. Neither workflow can cancel
the other after lifecycle work starts.

## Trust, secrets, and state

GitHub OIDC exchanges the approved job identity for short-lived AWS
credentials. No static AWS access key is committed or stored as a GitHub
secret. The Environment holds only the lifecycle role ARN, expected account ID,
and remote-state bucket name; the region is an Environment variable. The job
masks these inputs and all identifiers extracted from Terraform before use.

The role trust is constrained to the repository identity, `main`, the
`assessment-aws` Environment, and the exact deploy/destroy workflow files. Its
inline policy grants the application lifecycle actions rather than an AWS
managed administrator policy. Region, exact-resource, project-tag, and service
conditions are used where the AWS authorization model supports them.

Application state uses the bootstrap-managed versioned, encrypted S3 bucket and
native S3 lock file. Workflows create the backend configuration, saved plans,
state JSON, and raw logs only below `${RUNNER_TEMP}` with private permissions;
they are never artifacts. `bootstrap/` remains a separate local-state root
because it creates the backend that `infra/` consumes. Destroying `infra/` never
destroys bootstrap storage, the OIDC provider, or the lifecycle role.

## Simplified deployment sequence

The deploy workflow keeps two Terraform phases because the first creation plan
cannot always know the ECR repository URL until AWS creates the repository. ECS
container definitions derive from that URL and the required full Git SHA. A
single live plan would either refer to an image that cannot yet be pushed or
weaken the immutable-image invariant. The zero-task boundary solves the ordering
problem without running an unverified container.

1. Refuse non-`main` or incorrect `DEPLOY platform-assessment` input.
2. Discover one runner IPv4 `/32`, mask it, obtain OIDC credentials, verify the
   expected account privately, and initialize the remote backend.
3. Save and validate a zero-task plan. The policy permits only the exact
   application allowlist, desired count `0`, the runner-rule transition, and the
   known task-definition replacement. An unknown first-create container
   definition is accepted only when Terraform marks it unknown and source
   expressions still reference the managed ECR URL plus exact full SHA.
4. Apply that exact plan. This creates the repository and infrastructure but no
   running task.
5. Build `linux/amd64`, block High/Critical Trivy findings, and run the exact
   full-SHA image locally with a read-only filesystem, all capabilities dropped,
   `no-new-privileges`, UID/GID `10001:10001`, Docker health, HTTP `200`, and the
   exact health body.
6. Push only the immutable full-SHA tag. If it already exists, pull the resolved
   digest, prove the OCI revision label, scan it, and run the same hardened test.
7. Save and validate the live plan with desired count `1`. Only the allowed ECS
   service/task-definition transition may change, and container definitions
   must concretely use the expected full SHA.
8. Apply that exact plan and perform the small final gate described below.
9. Remove private runner files and local containers on success or failure.

### Final blocking validation

The application is accepted only when all six checks pass:

1. `aws ecs wait services-stable` succeeds.
2. Exactly one running task is returned for the service.
3. That task's `lastStatus` is `RUNNING`.
4. Exactly one ALB target is present and its state is `healthy`.
5. `GET /health` returns HTTP `200`.
6. The response body is exactly `{"status":"healthy"}`.

The task definition also has a simple Python-standard-library ECS health check,
but ECS `healthStatus` is not a separate final blocker. Service stability, ALB
health, and the direct contract test provide the understandable deployment
gate. CloudWatch logging remains configured through the `awslogs` driver and is
an operational observation rather than a deployment dependency. The previous
extra five-request loop and blocking log search were removed.

## Simplified destruction sequence

The destroy workflow remains independent and manual. It requires
`DESTROY platform-assessment` plus the exact currently deployed 40-character
SHA.

1. Guard `main`, input format, protected Environment, OIDC identity, and shared
   lifecycle concurrency.
2. Read remote state privately and prove the expected image SHA, managed
   identities, and current runner CIDR.
3. Save, validate, and apply the exact scale-to-zero plan; wait until running
   and pending task counts are both zero.
4. Save a Terraform `-destroy` plan and reject it unless every active managed
   change is a deletion of an allowlisted `infra/` resource.
5. Apply that exact saved destroy plan.
6. Require application state to contain zero managed resources and independently
   confirm sanitized absence booleans/counts for ECR, ECS, ALB, NAT Gateway, and
   Elastic IP.
7. Remove private runner files on success or failure.

The ECR repository uses `force_delete = true`. This is acceptable here because
the repository is disposable, project-named, Terraform-managed, protected by a
manual Environment approval, and deleted only inside a fail-closed whole-stack
destroy plan. Images are immutable release artifacts but are not the system of
record; Git and CI can reproduce them. Production repositories with retention,
forensics, or rollback requirements should instead use lifecycle policies and a
separately approved retention process.

Explicit ECR inventory, digest-batch generation, image deletion, and empty-
repository steps are unnecessary with Terraform-owned `force_delete`. Removing
them also eliminates a second deletion authority and leaves one reviewed saved
plan as the source of truth.

### Destroy failure and recovery detail

The latest automated destroy removed 31 of 32 application resources, but the
workflow did not complete successfully. The final Elastic IP operation failed
because `ec2:DisassociateAddress` also required authorization for the
AWS-managed NAT network interface, which does not inherit the project's
`Project` tag. A reviewed, exact single-resource Terraform recovery plan then
removed the Elastic IP. Final application state contains zero managed resources,
and no project Elastic IP remains.

The first IAM regression correction used separate statements for the two
resource types, but AWS rejected that inline-policy update atomically because
the lifecycle role's aggregate inline policy exceeded the non-adjustable quota.
The compact final statement instead authorizes only
`ec2:DisassociateAddress` against the account-and-region Elastic IP and network-
interface ARN patterns. It retains the exact regional restriction and avoids a
wildcard resource. The tradeoff is that it cannot require the `Project` resource
tag because the AWS-managed NAT network interface does not inherit that tag.
That compact correction is now live and was verified by a no-change bootstrap
plan and IAM simulation for representative resources of both required types.

## Failure and recovery boundary

A failure never triggers automatic destroy, state mutation, force-unlock, or a
broader retry. The workflow prints only a sanitized warning, retains remote
state, and requires a separately reviewed reconciliation. Saved plans are never
reused across commits or workflow runs. A failed run must not be rerun if its
original commit contains an obsolete policy; dispatch a new run from the fixed
`main` commit instead.

The application cost timer starts when chargeable application infrastructure is
created and ends only after absence is independently verified. For this
lifecycle, it ended after the one-resource recovery and final empty-state and
inventory checks—not when the failed destroy workflow stopped. NAT Gateway,
ALB, public IPv4 allocation, Fargate, ECR, CloudWatch Logs, and data transfer may
incur charges during a deployment. Retained bootstrap resources are outside this
application timer.

## Lessons learned from live validation

- AWS actions do not all support the same resource scope. Account-level ECS
  reads, task-definition deregistration, cluster-filtered task listing, and S3
  bucket-location reads required purpose-specific statements.
- Terraform provider operations include reads that are easy to miss when
  reasoning only from create/delete APIs. Regression tests now inventory the
  exact IAM action set and statement conditions.
- A failed apply can partially create resources and mark interrupted resources
  tainted. Recovery must compare state and cloud reality before changing taint.
- A `for_each` runner CIDR change appears as one old instance deletion and one
  new instance creation, not a same-address replacement. The plan policy allows
  only that exact pair.
- Private validation scripts still need explicit initialization; the original
  log-window timestamp omission made a later command unreliable.
- Copy/paste errors matter in shell workflows. An accidental duplicate ECS
  waiter became an AWS CLI syntax failure and now has an exactly-once test.
- `aws ecr batch-delete-image --image-ids file://...` expects a raw JSON list,
  not an object containing `imageIds`. The helper is corrected even though the
  simplified destroy no longer calls it.
- ECS task `healthStatus` must match task-definition semantics. The task now has
  an explicit health check, while the final gate relies on observable service,
  target, and HTTP outcomes.
- Final EIP cleanup requires `ec2:DisassociateAddress` for both the tagged
  Elastic IP and the AWS-managed NAT network interface. One compact regional
  statement covers both resource patterns without a wildcard; its exact action
  cannot use the `Project` tag condition because the managed interface is
  untagged.

These failures were fail-closed: raw private data was not published, bootstrap
resources were retained, each partial application was reconciled, and the
temporary application resources were cleaned up.

## Known limitations

- The deployment path completed successfully. The corrected final-EIP permission
  has a clean plan and IAM-simulation result, but the historical destroy workflow
  itself remains a failed run; only a future full lifecycle can provide a green
  end-to-end destroy execution.
- The assessment listener is temporary HTTP without a domain or TLS.
- One NAT Gateway and desired count `1` reduce cost but do not provide
  production multi-AZ availability.
- The runner's public `/32` is temporarily admitted to the ALB for validation;
  a production design should use private runners or a separate probe path.
- One lifecycle role serves deploy and destroy. Separate roles would provide
  stronger production separation of duties.
- Bootstrap local state requires private backup and a separately authorized
  retirement procedure.
- Action releases use stable version tags rather than reviewed commit digests.
