# Phase 3C continuous-delivery design

## Status

Checkpoint 1 and Checkpoint 2 are committed on `main`. CI run `#7` validated
both Terraform roots with all four jobs passing in 1 minute 30 seconds. The
bootstrap, protected GitHub Environment, OIDC trust, lifecycle role, and remote
application state backend are now configured.

The first gated deploy authenticated successfully and validated its zero-task
saved plan, but the apply stopped on least-privilege IAM defects. It created 10
managed application resources before failing and did not reach image
publication or the live ECS transition. There is no live endpoint, ECS task,
NAT Gateway, or ALB. One allocated Elastic IP remains chargeable. Deployment
and cleanup evidence are incomplete.

## Architecture and ownership boundary

Phase 3C separates long-lived delivery prerequisites from temporary application
infrastructure:

```text
authorized administrator
        |
        v
bootstrap/ local state
  |-- versioned SSE-S3 state bucket
  |-- GitHub OIDC provider (create or reuse)
  `-- one CD lifecycle IAM role
        |
        v
protected GitHub Environment: assessment-aws
        |
        v
manual-only main deploy or destroy workflow code
        |
        v
infra/ partial S3 backend -> application AWS resources
```

`bootstrap/` cannot use the bucket it creates: Terraform must initialize its
backend before it can create resources. Bootstrap state therefore remains
local, ignored, privately backed up, and operationally separate. Application
cleanup retains bootstrap so subsequent deployments can continue to access
state and obtain short-lived credentials.

## Identity and approval boundaries

GitHub OIDC replaces long-lived AWS access keys. The lifecycle role accepts
only `sts:AssumeRoleWithWebIdentity` from the exact configured GitHub provider.
Its trust requires the audience, immutable environment subject, repository
name, immutable repository and owner IDs, `main` ref, `assessment-aws`
environment, and one of the two exact workflow names. The immutable
subject format for this post-July-15-2026 repository is:

```text
repo:OWNER@OWNER-ID/REPOSITORY@REPOSITORY-ID:environment:assessment-aws
```

The real subject must be copied from verified repository identity data. The
jobs declare the protected environment, and GitHub must configure
required reviewers and restrict deployment branches to `main`. IAM claim
checks and GitHub environment rules are complementary; neither replaces the
other.

One role serves deploy and destroy to keep this assessment small. This makes
the trust and permission surface easier to audit, but either workflow receives
the union of lifecycle permissions after approval. Production systems should
prefer separate deploy/destroy roles or finer-grained stages when separation of
duties outweighs this simplicity.

## State protection

The application backend commits only a non-secret key, region, encryption flag,
and native `use_lockfile = true`. Each workflow writes the real bucket
name to a temporary `.tfbackend` file under `${RUNNER_TEMP}` and will never
publish that file, state, or plans as artifacts.

SSE-S3 (`AES256`) is sufficient for this bounded assessment and avoids a
customer-managed KMS key and its additional permissions, rotation, retention,
and cost. A production design with stronger key ownership or audit requirements
should use a customer-managed KMS key and a narrowly scoped key policy.

Native S3 lock files protect Terraform's state transaction. DynamoDB locking is
deprecated and unnecessary for this backend. GitHub workflow concurrency is a
separate protection layer: it controls workflow scheduling, while S3 locking
protects state even when work begins outside GitHub. Versioning supplies state
recovery; locking does not replace backups or version recovery.

## Remote-state migration — not yet performed

The Phase 2 environment is destroyed and the current application state is
local/empty, but migration still requires an explicit manual checkpoint:

1. Verify the application environment remains destroyed and take a private,
   integrity-checked backup of the current local state and any backup file.
2. Manually apply `bootstrap/` after reviewing account- and repository-specific
   inputs and a fresh plan.
3. Verify bucket versioning, encryption, public-access blocking, ownership,
   TLS-only policy, OIDC trust, and lifecycle policy in the intended account.
4. Supply the bootstrap-created bucket through a private temporary backend
   configuration and run Terraform's interactive backend migration manually.
5. Verify the remote state object and locking behavior without publishing state
   or plan content, then retain the private local backup until recovery has been
   tested.
6. Only after migration is reviewed should the protected workflows be enabled
   for deliberate manual execution.

Migration must never run automatically in CD, and state or plans must never be
uploaded as public GitHub artifacts.

## Deploy workflow — first execution stopped during zero-task apply

The ordinary workflow name is `Deploy application infrastructure`. It is
manual-dispatch only, refuses a non-`main` ref or anything except the typed
confirmation `DEPLOY platform-assessment`, declares `assessment-aws`, and
shares queued lifecycle concurrency with destroy.

Its static sequence discovers and masks the runner IPv4 `/32`, obtains bounded
OIDC credentials, verifies the expected account privately, initializes the
temporary backend, validates a saved zero-task plan, and applies that exact
plan. It then builds, scans, and hardens the exact full-SHA image locally. ECR
publication is immutable and retry-bounded; an existing SHA is pulled by digest
and must have the matching OCI revision label before the same scan/runtime
gates pass. A second saved plan may change only the approved ECS live
transition. Post-apply checks emit only whitelisted ECS, task, target, HTTP, and
CloudWatch summaries. Failure never triggers automatic destruction or state
force-unlocking. The first execution exercised this behavior: it stopped before
image publication when the zero-task apply encountered insufficient
lifecycle-role permissions.

The repository IAM correction broadens only unsupported-resource-scope reads
and tagged EC2 dependency authorization. It is not yet applied. A read-only
reconciliation plan also found three tainted resources that would be replaced;
the existing bootstrap policy guard rejects those deletions. An administrator
must review IAM application and taint recovery separately before another
workflow dispatch.

## Destroy workflow — implemented, not executed

The ordinary workflow name is `Destroy application infrastructure`. It is
manual-dispatch only and requires both `DESTROY platform-assessment` and the
expected deployed full SHA. It is protected by the same environment,
restricted to `main`, and serialized against deploy.

The workflow proves the remote application state, image SHA, repository, and
current runner CIDR before a saved scale-zero transition. It waits for zero
tasks, rejects untagged or non-SHA images, deletes only validated digests in
batches of at most 100, then validates and applies a deletion-only saved plan.
Independent sanitized checks require the application ECR repository and ALB to
be absent, ECS inactive/absent, NAT absent/deleted, the EIP released, and zero
managed resources in application state. Bootstrap resources remain outside the
destroy root and are retained.

## Protected GitHub Environment and recovery sequence

The protected Environment is named exactly `assessment-aws`, uses required
reviewers, and restricts deployment to `main`.

Required Environment secrets:

- `AWS_ROLE_ARN`
- `AWS_ACCOUNT_ID`
- `TF_STATE_BUCKET`

Required Environment variable:

- `AWS_REGION=eu-central-1`

The current manual recovery sequence is:

1. Privately back up bootstrap and remote application state.
2. Review a bootstrap plan containing only the lifecycle-role inline-policy
   update, then apply it manually under separate authorization.
3. Verify the updated policy and its regional, tagging, trust, PassRole, and
   state boundaries.
4. Review the three tainted application resources and choose an explicit state
   recovery procedure; do not weaken the bootstrap plan guard.
5. Require a fresh zero-task plan with the existing resources preserved and no
   replacement or deletion before another deploy dispatch.
6. Create sanitized evidence only after a successful live execution.
7. When cleanup is approved, dispatch destroy with its typed confirmation and
   the exact deployed full SHA; record evidence only after verified cleanup.

## Logs, failure recovery, and cost

Public workflow logs must never print credentials, account IDs, ARNs, ECR URLs,
public IP addresses, backend files, Terraform state, raw outputs, or saved
plans. `sensitive = true` suppresses ordinary Terraform output display but does
not remove values from state. Workflows must use explicitly private handling
instead of unfiltered `terraform output`.

If deployment fails, preserve the remote state lock until Terraform exits,
inspect sanitized diagnostics, rely on the ECS circuit breaker for an existing
healthy revision, and rerun only after reconciling state and cloud reality. Use
S3 object versions for reviewed state recovery; never delete a lock while an
operation may still be active. Manual recovery remains approval-gated.

The bootstrap bucket, version storage, and IAM/OIDC objects are retained and
normally low cost. Application NAT Gateway, ALB, public IPv4, Fargate, ECR,
CloudWatch Logs, and transfer charges begin when the application stack is
created. The destroy workflow is the application cost timer boundary, but
bootstrap retention means “application destroyed” is not “AWS account empty.”

Exceptional bootstrap removal must be a separate administrator procedure after
application cleanup, retention review, state export/backup, and confirmation
that no workflow depends on the provider or role.
