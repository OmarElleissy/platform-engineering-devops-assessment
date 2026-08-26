variable "aws_region" {
  description = "AWS region in which to create the assessment infrastructure."
  type        = string
  default     = "eu-central-1"

  validation {
    condition     = var.aws_region == "eu-central-1"
    error_message = "The approved assessment region is eu-central-1."
  }
}

variable "name_prefix" {
  description = "Short, readable prefix applied to resource names."
  type        = string
  default     = "platform-assessment"

  validation {
    condition     = length(var.name_prefix) >= 3 && length(var.name_prefix) <= 20 && can(regex("^[a-z0-9]+(?:-[a-z0-9]+)*$", var.name_prefix))
    error_message = "name_prefix must be 3-20 lowercase alphanumeric or hyphen characters and cannot start or end with a hyphen."
  }
}

variable "availability_zones" {
  description = "Two distinct availability zones used for the public and private subnet pairs."
  type        = list(string)
  default     = ["eu-central-1a", "eu-central-1b"]

  validation {
    condition = (
      length(var.availability_zones) == 2 &&
      length(distinct(var.availability_zones)) == 2 &&
      alltrue([for zone in var.availability_zones : can(regex("^eu-central-1[a-z]$", zone))])
    )
    error_message = "Provide two distinct availability zones in eu-central-1."
  }
}

variable "vpc_cidr" {
  description = "IPv4 CIDR assigned to the assessment VPC."
  type        = string
  default     = "10.20.0.0/16"

  validation {
    condition     = var.vpc_cidr == "10.20.0.0/16"
    error_message = "The approved VPC CIDR is 10.20.0.0/16."
  }
}

variable "public_subnet_cidrs" {
  description = "IPv4 CIDRs assigned to the two public subnets."
  type        = list(string)
  default     = ["10.20.0.0/24", "10.20.1.0/24"]

  validation {
    condition     = var.public_subnet_cidrs == tolist(["10.20.0.0/24", "10.20.1.0/24"])
    error_message = "The approved public subnet CIDRs are 10.20.0.0/24 and 10.20.1.0/24."
  }
}

variable "private_subnet_cidrs" {
  description = "IPv4 CIDRs assigned to the two private subnets."
  type        = list(string)
  default     = ["10.20.10.0/24", "10.20.11.0/24"]

  validation {
    condition     = var.private_subnet_cidrs == tolist(["10.20.10.0/24", "10.20.11.0/24"])
    error_message = "The approved private subnet CIDRs are 10.20.10.0/24 and 10.20.11.0/24."
  }
}

variable "allowed_http_cidrs" {
  description = "IPv4 CIDRs allowed to reach the temporary public HTTP listener."
  type        = set(string)
  default     = ["0.0.0.0/0"]

  validation {
    condition = (
      length(var.allowed_http_cidrs) > 0 &&
      alltrue([
        for cidr in var.allowed_http_cidrs :
        can(cidrnetmask(cidr)) && length(regexall(":", cidr)) == 0
      ])
    )
    error_message = "allowed_http_cidrs must contain at least one valid IPv4 CIDR."
  }
}

variable "container_port" {
  description = "Application container and target-group port."
  type        = number
  default     = 8080

  validation {
    condition     = var.container_port == 8080
    error_message = "The application listens on the approved port 8080."
  }
}

variable "task_cpu" {
  description = "Fargate task CPU units."
  type        = number
  default     = 256

  validation {
    condition     = var.task_cpu == 256
    error_message = "The approved assessment task size uses 256 CPU units."
  }
}

variable "task_memory" {
  description = "Fargate task memory in MiB."
  type        = number
  default     = 512

  validation {
    condition     = var.task_memory == 512
    error_message = "The approved assessment task size uses 512 MiB of memory."
  }
}

variable "image_tag" {
  description = "Immutable ECR image tag used by the task definition."
  type        = string
  default     = "bootstrap"

  validation {
    condition = (
      lower(var.image_tag) != "latest" &&
      length(var.image_tag) <= 128 &&
      can(regex("^[A-Za-z0-9_][A-Za-z0-9._-]*$", var.image_tag))
    )
    error_message = "image_tag must be a valid non-latest Docker tag of at most 128 characters."
  }
}

variable "desired_count" {
  description = "Number of application tasks; start at zero and change to one only after the image is pushed."
  type        = number
  default     = 0

  validation {
    condition     = floor(var.desired_count) == var.desired_count && contains([0, 1], var.desired_count)
    error_message = "desired_count must be either 0 for bootstrap or 1 after the image is available."
  }
}

variable "health_check_path" {
  description = "HTTP path used by ECS and the ALB to check application health."
  type        = string
  default     = "/health"

  validation {
    condition     = var.health_check_path == "/health"
    error_message = "The approved application health-check path is /health."
  }
}

variable "log_retention_days" {
  description = "CloudWatch Logs retention period."
  type        = number
  default     = 7

  validation {
    condition     = var.log_retention_days == 7
    error_message = "The approved log retention period is seven days."
  }
}

variable "additional_tags" {
  description = "Additional non-sensitive tags merged with the standard assessment tags."
  type        = map(string)
  default     = {}
}
