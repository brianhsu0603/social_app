variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-east-1"
}

variable "project" {
  description = "Project name used as a prefix on all resource names"
  type        = string
  default     = "social"
}

variable "environment" {
  description = "Deployment environment (production, staging)"
  type        = string
  default     = "production"
}

variable "domain_name" {
  description = "Root domain for Route53 and ACM (e.g. example.com)"
  type        = string
  default     = "example.com"
}

variable "vpc_cidr" {
  type    = string
  default = "10.0.0.0/16"
}

# ── EKS ──────────────────────────────────────────────────────────────────────

variable "eks_version" {
  description = "Kubernetes version for the EKS cluster"
  type        = string
  default     = "1.30"
}

variable "eks_general_instance_types" {
  description = "Instance types for the general-purpose node group (API pods, workers)"
  type        = list(string)
  default     = ["m5.large"]
}

variable "eks_compute_instance_types" {
  description = "Instance types for the compute node group (transcode workers)"
  type        = list(string)
  default     = ["c5.2xlarge"]
}

# ── RDS ──────────────────────────────────────────────────────────────────────

variable "rds_instance_class" {
  type    = string
  default = "db.r6g.large"
}

variable "rds_allocated_storage" {
  type    = number
  default = 50
}

variable "rds_max_allocated_storage" {
  description = "Upper bound (GB) for RDS storage autoscaling"
  type        = number
  default     = 300
}

variable "rds_username" {
  type      = string
  default   = "social"
  sensitive = true
}

variable "rds_password" {
  description = "Master password for RDS PostgreSQL — supply via TF_VAR_rds_password"
  type        = string
  sensitive   = true
}

# ── ElastiCache ───────────────────────────────────────────────────────────────

variable "elasticache_node_type" {
  type    = string
  default = "cache.r6g.large"
}

variable "elasticache_auth_token" {
  description = "Redis AUTH token (16-128 chars) — supply via TF_VAR_elasticache_auth_token"
  type        = string
  sensitive   = true
}

# ── DocumentDB ───────────────────────────────────────────────────────────────

variable "docdb_instance_class" {
  type    = string
  default = "db.r6g.large"
}

variable "docdb_username" {
  type      = string
  default   = "social"
  sensitive = true
}

variable "docdb_password" {
  description = "Master password for DocumentDB — supply via TF_VAR_docdb_password"
  type        = string
  sensitive   = true
}

# ── MSK ──────────────────────────────────────────────────────────────────────

variable "msk_instance_type" {
  type    = string
  default = "kafka.m5.large"
}

variable "msk_ebs_volume_size" {
  description = "EBS volume size (GB) per MSK broker"
  type        = number
  default     = 200
}

variable "msk_username" {
  description = "SASL/SCRAM username for MSK — supply via TF_VAR_msk_username"
  type        = string
  default     = "social"
  sensitive   = true
}

variable "msk_password" {
  description = "SASL/SCRAM password for MSK — supply via TF_VAR_msk_password"
  type        = string
  sensitive   = true
}
