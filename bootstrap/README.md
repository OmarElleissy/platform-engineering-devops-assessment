# Phase 3C bootstrap foundation

This separate Terraform root defines the long-lived prerequisites for future
application delivery. It has deliberately local state and must be operated
manually by an authorized administrator. Checkpoint 1 has not run this root and
has not created AWS or GitHub resources.

## Resources

The root defines:

- one S3 state bucket with versioning, SSE-S3 (`AES256`),
  bucket-owner-enforced ownership, complete public-access blocking, a TLS-only
  bucket policy, `force_destroy = false`, and Terraform `prevent_destroy`;
- one GitHub Actions OIDC provider when `create_github_oidc_provider = true`,
  or an exact existing provider ARN when it is false; and
- one IAM lifecycle role with one inline least-privilege policy for the future
  deploy and destroy workflows.

The bootstrap root has no backend block because a Terraform configuration
cannot safely store its own state in a bucket that does not exist until after
that configuration is applied. Its local state and backups must remain ignored,
private, backed up separately, and retained after application cleanup.

## Inputs and private handling

Copy `terraform.tfvars.example` to ignored `terraform.tfvars` only during a
future authorized bootstrap operation. Replace every synthetic value with
verified values. Never commit the resulting file, local state, plans, account
identifiers, role ARNs, bucket names, credentials, or tokens.

The state bucket name must be globally unique. `state_key` is fixed to
`platform-assessment/terraform.tfstate`, which matches `infra/backend.tf`.
The standard `Owner`, `Project`, `Environment`, and `ManagedBy` tags are set at
provider level and cannot be overridden by another input.

GitHub repositories created after July 15, 2026 use an immutable default OIDC
subject containing owner and repository IDs. For the protected environment,
the required exact form is:

```text
repo:OWNER@OWNER-ID/REPOSITORY@REPOSITORY-ID:environment:assessment-aws
```

Obtain the numeric IDs and exact subject from the intended repository; do not
derive them from a commit timestamp or invent them. The variable validation
requires the subject to match the separately supplied names, IDs, and
environment.

## OIDC trust boundary

The role trusts only the selected
`token.actions.githubusercontent.com` provider and only
`sts:AssumeRoleWithWebIdentity`. Every token must have all of these exact
claims:

- audience `sts.amazonaws.com`;
- the immutable environment subject supplied above;
- the expected `owner/repository`, repository ID, and owner ID;
- `ref` equal to `refs/heads/main`;
- environment `assessment-aws`; and
- workflow name equal to `Deploy application infrastructure` or
  `Destroy application infrastructure`.

Those names are reserved for the ordinary Checkpoint 2 workflows. The trust
uses the supported `workflow` claim and does not use `job_workflow_ref`, which
is intended for reusable-workflow identity. GitHub environment protection must
still be configured in GitHub before either future workflow can authenticate.

No thumbprint is hardcoded. Current AWS IAM behavior uses AWS's trusted CA
library for GitHub, and the current HashiCorp AWS provider makes
`thumbprint_list` optional. Omitting it avoids coupling the configuration to an
obsolete certificate thumbprint. See the official
[AWS IAM OIDC condition keys](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_iam-condition-keys.html),
[GitHub immutable subject reference](https://docs.github.com/en/actions/reference/security/oidc),
and [Terraform AWS provider resource](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_openid_connect_provider).

## Lifecycle permissions

The inline role policy limits state access to the exact bucket, state object,
and native `${state_key}.tflock` object. The state object can be read and
written but not deleted; only the lock object can be deleted. The role cannot
change bucket encryption, versioning, policy, ownership, public-access
controls, or the bootstrap role itself.

Application permissions cover the deterministic assessment ECR repository,
ECS cluster/service/task family, ALB and target-group name patterns, ECS
execution role, and CloudWatch log group. `iam:PassRole` is limited to the exact
execution-role ARN and `ecs-tasks.amazonaws.com`. Region conditions pin
regional activity to `eu-central-1`; request/resource project-tag conditions
are applied where the service supports them.

Some AWS APIs cannot be narrowed to a pre-existing ARN or do not support
resource-level authorization:

- `ecr:GetAuthorizationToken`, ECS list operations, regional EC2/ELB discovery,
  and CloudWatch Logs group discovery require `Resource: "*"`;
- ECS task-definition registration has no existing task-definition ARN and is
  constrained by region and the mandatory `Project` request tag;
- ALB and target-group creation occur before their generated ARN suffixes are
  known and are constrained by region and the mandatory project request tag;
- EC2 creates and untagged relationship operations (routes, route-table
  associations, gateway attachments, and security-group rules) require broad
  resource scope, so they are constrained by region and, for taggable creates,
  the mandatory project request tag;
- EC2 describes require broad resource scope and are region constrained; and
- first use may require creation of the AWS-managed ECS or ELB service-linked
  role, constrained by the exact `iam:AWSServiceName` values.

The role does not have AdministratorAccess, cannot pass an arbitrary role,
cannot manage unrelated IAM roles, and has no access to unrelated state
objects, ECR repositories, or log groups. Live Checkpoint 2 testing must verify
that this policy is both sufficient and still least-privileged; no such test has
occurred yet.

## Validation and future operation

Safe offline validation does not need real variable values:

```bash
terraform fmt -check -recursive bootstrap
terraform -chdir=bootstrap init -backend=false -input=false
terraform -chdir=bootstrap validate -no-color
```

A future authorized bootstrap operation must first review a plan, retain a
private backup of local bootstrap state, and apply manually. It must not be
folded into application CD. Sensitive outputs reduce ordinary terminal display
but remain in Terraform state and therefore require the same private handling.

Application destroy must leave this bootstrap root, its local state backup, the
state bucket, OIDC provider, and lifecycle role intact. Removing bootstrap is a
separate exceptional operation requiring confirmation that application state
and every retained version are no longer needed; `prevent_destroy` must never
be bypassed casually.
