output "account_id" {
  description = "AWS account containing the bootstrap resources."
  value       = data.aws_caller_identity.current.account_id
  sensitive   = true
}

output "cd_role_arn" {
  description = "Lifecycle role ARN for the future GitHub Actions deploy and destroy workflows."
  value       = aws_iam_role.cd_lifecycle.arn
  sensitive   = true
}

output "state_bucket_name" {
  description = "S3 bucket containing application Terraform state."
  value       = aws_s3_bucket.terraform_state.id
  sensitive   = true
}

output "github_oidc_provider_arn" {
  description = "GitHub Actions OIDC provider ARN created or reused by this bootstrap root."
  value       = local.oidc_provider_arn
  sensitive   = true
}

output "application_state_key" {
  description = "S3 object key used for application Terraform state."
  value       = var.state_key
  sensitive   = true
}
