provider "aws" {
  region = var.aws_region

  default_tags {
    tags = merge(local.default_tags, var.additional_tags)
  }
}
