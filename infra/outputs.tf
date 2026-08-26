output "aws_region" {
  description = "AWS region containing the assessment infrastructure."
  value       = var.aws_region
}

output "vpc_id" {
  description = "ID of the assessment VPC."
  value       = aws_vpc.this.id
}

output "public_subnet_ids" {
  description = "Ordered IDs of the public subnets."
  value       = [for key in sort(keys(aws_subnet.public)) : aws_subnet.public[key].id]
}

output "private_subnet_ids" {
  description = "Ordered IDs of the private subnets."
  value       = [for key in sort(keys(aws_subnet.private)) : aws_subnet.private[key].id]
}

output "ecr_repository_name" {
  description = "Name of the private application image repository."
  value       = aws_ecr_repository.app.name
}

output "ecr_repository_url" {
  description = "URL to use when tagging and pushing the application image."
  value       = aws_ecr_repository.app.repository_url
}

output "ecs_cluster_name" {
  description = "Name of the ECS cluster."
  value       = aws_ecs_cluster.app.name
}

output "ecs_service_name" {
  description = "Name of the ECS service."
  value       = aws_ecs_service.app.name
}

output "ecs_task_definition_arn" {
  description = "ARN of the current ECS task-definition revision."
  value       = aws_ecs_task_definition.app.arn
}

output "cloudwatch_log_group_name" {
  description = "CloudWatch Logs group receiving application container logs."
  value       = aws_cloudwatch_log_group.app.name
}

output "alb_dns_name" {
  description = "Public DNS name assigned to the application load balancer."
  value       = aws_lb.app.dns_name
}

output "application_url" {
  description = "Temporary plaintext HTTP endpoint for the assessment."
  value       = "http://${aws_lb.app.dns_name}"
}
