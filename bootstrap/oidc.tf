resource "aws_iam_openid_connect_provider" "github" {
  count = var.create_github_oidc_provider ? 1 : 0

  url            = local.github_oidc_url
  client_id_list = ["sts.amazonaws.com"]

  tags = {
    Name = "github-actions"
  }
}

data "aws_iam_policy_document" "cd_assume_role" {
  statement {
    sid     = "GitHubActionsLifecycleWorkflows"
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [local.oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.github_oidc_namespace}:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.github_oidc_namespace}:sub"
      values   = [var.github_oidc_subject]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.github_oidc_namespace}:repository"
      values   = ["${var.github_owner}/${var.github_repository}"]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.github_oidc_namespace}:repository_id"
      values   = [var.github_repository_id]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.github_oidc_namespace}:repository_owner_id"
      values   = [var.github_owner_id]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.github_oidc_namespace}:ref"
      values   = ["refs/heads/main"]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.github_oidc_namespace}:environment"
      values   = [var.github_environment]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.github_oidc_namespace}:workflow"
      values   = local.allowed_workflows
    }
  }
}
