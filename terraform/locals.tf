locals {
  name = "${var.project}-${var.environment}"

  # Use the first 3 available AZs in the region
  azs = slice(data.aws_availability_zones.available.names, 0, 3)

  # Subnet CIDRs — three tiers across three AZs
  public_subnets   = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
  private_subnets  = ["10.0.11.0/24", "10.0.12.0/24", "10.0.13.0/24"]
  database_subnets = ["10.0.21.0/24", "10.0.22.0/24", "10.0.23.0/24"]

  # Stripped OIDC issuer URL (no https://) used in IRSA trust policies
  oidc_issuer = replace(aws_iam_openid_connect_provider.eks.url, "https://", "")

  common_tags = {
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}
