variable "aws_region" {
  description = "AWS region containing the assessment resources and application state bucket."
  type        = string

  validation {
    condition     = var.aws_region == "eu-central-1"
    error_message = "The approved assessment region is eu-central-1."
  }
}

variable "state_bucket_name" {
  description = "Globally unique name for the S3 bucket that will store application Terraform state."
  type        = string

  validation {
    condition = (
      length(var.state_bucket_name) >= 3 &&
      length(var.state_bucket_name) <= 63 &&
      can(regex("^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$", var.state_bucket_name)) &&
      !strcontains(var.state_bucket_name, "--") &&
      !can(regex("^[0-9]+\\.[0-9]+\\.[0-9]+\\.[0-9]+$", var.state_bucket_name))
    )
    error_message = "state_bucket_name must be a valid 3-63 character, globally unique S3 bucket name using lowercase letters, numbers, and single hyphens."
  }
}

variable "state_key" {
  description = "Dedicated S3 object key for application Terraform state."
  type        = string

  validation {
    condition     = var.state_key == "platform-assessment/terraform.tfstate"
    error_message = "state_key must be platform-assessment/terraform.tfstate so it matches infra/backend.tf."
  }
}

variable "github_owner" {
  description = "GitHub repository owner name."
  type        = string

  validation {
    condition     = can(regex("^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$", var.github_owner))
    error_message = "github_owner must be a valid GitHub owner name."
  }
}

variable "github_owner_id" {
  description = "Immutable numeric GitHub repository-owner ID."
  type        = string

  validation {
    condition     = can(regex("^[1-9][0-9]*$", var.github_owner_id))
    error_message = "github_owner_id must be a positive numeric GitHub owner ID."
  }
}

variable "github_repository" {
  description = "GitHub repository name."
  type        = string

  validation {
    condition     = length(var.github_repository) >= 1 && length(var.github_repository) <= 100 && can(regex("^[A-Za-z0-9._-]+$", var.github_repository))
    error_message = "github_repository must be a valid 1-100 character GitHub repository name."
  }
}

variable "github_repository_id" {
  description = "Immutable numeric GitHub repository ID."
  type        = string

  validation {
    condition     = can(regex("^[1-9][0-9]*$", var.github_repository_id))
    error_message = "github_repository_id must be a positive numeric GitHub repository ID."
  }
}

variable "github_environment" {
  description = "Protected GitHub Environment required by the lifecycle workflows."
  type        = string
  default     = "assessment-aws"

  validation {
    condition     = var.github_environment == "assessment-aws"
    error_message = "github_environment must remain assessment-aws for this checkpoint."
  }
}

variable "github_oidc_subject" {
  description = "Exact immutable GitHub environment subject containing the owner and repository IDs."
  type        = string

  validation {
    condition = var.github_oidc_subject == format(
      "repo:%s@%s/%s@%s:environment:%s",
      var.github_owner,
      var.github_owner_id,
      var.github_repository,
      var.github_repository_id,
      var.github_environment,
    )
    error_message = "github_oidc_subject must exactly match repo:OWNER@OWNER-ID/REPO@REPO-ID:environment:assessment-aws using the supplied immutable IDs."
  }
}

variable "create_github_oidc_provider" {
  description = "Whether bootstrap should create the account-level GitHub Actions OIDC provider."
  type        = bool
}

variable "existing_oidc_provider_arn" {
  description = "Existing GitHub Actions OIDC provider ARN when provider creation is disabled."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition = var.create_github_oidc_provider ? (
      var.existing_oidc_provider_arn == null
      ) : (
      var.existing_oidc_provider_arn != null &&
      can(regex("^arn:[a-z0-9-]+:iam::[0-9]{12}:oidc-provider/token\\.actions\\.githubusercontent\\.com$", var.existing_oidc_provider_arn))
    )
    error_message = "Set existing_oidc_provider_arn to null when creating the provider, or supply the exact existing GitHub OIDC provider ARN when creation is disabled."
  }
}

variable "cd_role_name" {
  description = "Name of the single GitHub Actions lifecycle role used by future deploy and destroy workflows."
  type        = string

  validation {
    condition     = length(var.cd_role_name) >= 1 && length(var.cd_role_name) <= 64 && can(regex("^[A-Za-z0-9+=,.@_-]+$", var.cd_role_name))
    error_message = "cd_role_name must be a valid IAM role name of at most 64 characters."
  }
}

variable "owner_tag" {
  description = "Non-sensitive owner value applied as a mandatory standard tag."
  type        = string

  validation {
    condition     = length(trimspace(var.owner_tag)) >= 3 && length(var.owner_tag) <= 64 && !can(regex("(?i)(secret|token|password|credential|access.?key)", var.owner_tag))
    error_message = "owner_tag must be a 3-64 character non-sensitive ownership label."
  }
}

variable "project_tag" {
  description = "Mandatory project tag shared by bootstrap and application resources."
  type        = string

  validation {
    condition     = var.project_tag == "platform-assessment"
    error_message = "project_tag must remain platform-assessment so IAM tag conditions match the application resources."
  }
}
