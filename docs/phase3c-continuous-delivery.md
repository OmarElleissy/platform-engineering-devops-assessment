# Phase 3C continuous-delivery design

## Status

Checkpoint 1 implements repository foundations only. The bootstrap and
application configurations have not been planned against, applied to, or
queried in AWS. No GitHub Environment, OIDC trust, role, bucket, workflow, or
registry integration has been configured. Deploy and destroy workflows and CD
evidence remain intentionally absent until Checkpoint 2 and successful live
executions.

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
future main-only deploy or destroy workflow
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
environment, and one of the two exact future workflow names. The immutable
subject format for this post-July-15-2026 repository is:

```text
repo:OWNER@OWNER-ID/REPOSITORY@REPOSITORY-ID:environment:assessment-aws
```

The real subject must be copied from verified repository identity data. The
future jobs must declare the protected environment, and GitHub must configure
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
and native `use_lockfile = true`. A future workflow will write the real bucket
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
6. Only after migration is reviewed should Checkpoint 2 CD be enabled.

Migration must never run automatically in CD, and state or plans must never be
uploaded as public GitHub artifacts.

## Future deploy workflow

The future ordinary workflow name is `Deploy application infrastructure`. It
will run only for the protected `assessment-aws` environment from `main`, obtain
short-lived AWS credentials through OIDC, build and scan the exact commit image,
push the full 40-character Git SHA to the immutable assessment ECR repository,
initialize the private backend, review/apply that same SHA, wait for ECS/ALB
health, and emit only sanitized evidence. It will never use `latest`, a short
SHA, or a branch tag.

## Future destroy workflow

The future ordinary workflow name is `Destroy application infrastructure`. It
will be independently manual, protected by the same environment, restricted to
`main`, and serialized against deploy. It will confirm the intended state,
destroy only `infra/`, handle the non-empty ECR safety boundary deliberately,
verify cleanup without exposing identifiers, and retain all bootstrap
resources. It will not bypass the bootstrap bucket's `prevent_destroy` guard.

Neither workflow exists at Checkpoint 1.

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
