terraform {
  required_version = ">= 1.7"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.50"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
  }

  # Bootstrap: create the bucket and DynamoDB table once before `terraform init`.
  #   aws s3api create-bucket --bucket social-app-terraform-state --region us-east-1
  #   aws s3api put-bucket-versioning --bucket social-app-terraform-state \
  #       --versioning-configuration Status=Enabled
  #   aws dynamodb create-table --table-name social-app-terraform-lock \
  #       --attribute-definitions AttributeName=LockID,AttributeType=S \
  #       --key-schema AttributeName=LockID,KeyType=HASH \
  #       --billing-mode PAY_PER_REQUEST
  backend "s3" {
    bucket         = "social-app-terraform-state-995679261252"
    key            = "social-app/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "social-app-terraform-lock"
    encrypt        = true
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = local.common_tags
  }
}

data "aws_availability_zones" "available" {
  state = "available"
}

data "aws_caller_identity" "current" {}
