locals {
  container_name = "app"
  log_group_name = "/ecs/${var.name_prefix}"

  default_tags = {
    Environment = "assessment"
    ManagedBy   = "Terraform"
    Project     = var.name_prefix
  }

  public_subnets = {
    a = {
      availability_zone = var.availability_zones[0]
      cidr_block        = var.public_subnet_cidrs[0]
    }
    b = {
      availability_zone = var.availability_zones[1]
      cidr_block        = var.public_subnet_cidrs[1]
    }
  }

  private_subnets = {
    a = {
      availability_zone = var.availability_zones[0]
      cidr_block        = var.private_subnet_cidrs[0]
    }
    b = {
      availability_zone = var.availability_zones[1]
      cidr_block        = var.private_subnet_cidrs[1]
    }
  }
}
