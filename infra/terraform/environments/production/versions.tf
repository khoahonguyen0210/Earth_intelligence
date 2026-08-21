terraform {
  # use_lockfile (S3-native state locking) needs >= 1.10; pinned to the
  # minor this layout was validated with (docs/terraform-layout.md).
  required_version = "~> 1.16"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.66"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 3.3"
    }
  }

  # Partial configuration: the state bucket name contains the AWS account
  # ID, so it lives in a gitignored backend.hcl (see backend.hcl.example),
  # passed as `terraform init -backend-config=backend.hcl`.
  backend "s3" {
    key          = "production/terraform.tfstate"
    region       = "us-west-2"
    encrypt      = true
    use_lockfile = true
  }
}
