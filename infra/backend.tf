terraform {
  backend "s3" {
    key          = "platform-assessment/terraform.tfstate"
    region       = "eu-central-1"
    encrypt      = true
    use_lockfile = true
  }
}
