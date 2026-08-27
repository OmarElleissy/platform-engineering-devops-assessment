locals {
  github_oidc_url       = "https://token.actions.githubusercontent.com"
  github_oidc_namespace = "token.actions.githubusercontent.com"

  deploy_workflow_name  = "Deploy application infrastructure"
  destroy_workflow_name = "Destroy application infrastructure"
  allowed_workflows = [
    local.deploy_workflow_name,
    local.destroy_workflow_name,
  ]

  application_name_prefix = "platform-assessment"
  ecr_repository_name     = "${local.application_name_prefix}-app"
  ecs_cluster_name        = "${local.application_name_prefix}-cluster"
  ecs_service_name        = "${local.application_name_prefix}-service"
  ecs_task_family         = "${local.application_name_prefix}-task"
  ecs_execution_role_name = "${local.application_name_prefix}-ecs-execution"
  log_group_name          = "/ecs/${local.application_name_prefix}"

  standard_tags = {
    Environment = "assessment"
    ManagedBy   = "Terraform"
    Owner       = var.owner_tag
    Project     = var.project_tag
  }

  oidc_provider_arn = var.create_github_oidc_provider ? one(aws_iam_openid_connect_provider.github[*].arn) : var.existing_oidc_provider_arn
}
