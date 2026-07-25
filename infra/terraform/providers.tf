######################################################################
# SafeSpare AI — Terraform providers
#
# NOTE (honesty flag — see IMPLEMENTATION_STATUS.md §7):
# `terraform` is NOT installed on the machine this HCL was authored on.
# This file has been reviewed by eye for correctness and internal
# consistency but has never been through `terraform init` / `validate` /
# `plan`. Treat it as "believed correct, unverified" until a human with
# Terraform installed runs the commands in infra/scripts/deploy.sh.
######################################################################

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Local state by default so the project runs with zero extra setup during
  # the hackathon. Once you deploy for real, uncomment and point this at a
  # private S3 bucket + DynamoDB lock table (created once, by hand or in a
  # bootstrap stack) so state isn't just a file on one laptop.
  #
  # backend "s3" {
  #   bucket         = "CHANGE-ME-safespare-tfstate"
  #   key            = "safespare/terraform.tfstate"
  #   region         = "us-east-1"
  #   dynamodb_table = "CHANGE-ME-safespare-tflock"
  #   encrypt        = true
  # }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = local.common_tags
  }
}

# Route 53 publishes HealthCheckStatus to us-east-1 only, no matter where
# the rest of the stack lives, so the health alarm in monitoring.tf (and the
# SNS topic it notifies) must be created there. When var.aws_region is
# already us-east-1 this alias simply points at the same region.
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"

  default_tags {
    tags = local.common_tags
  }
}
