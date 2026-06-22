# ── EKS ──────────────────────────────────────────────────────────────────────

output "eks_cluster_name" {
  value = aws_eks_cluster.main.name
}

output "eks_cluster_endpoint" {
  value = aws_eks_cluster.main.endpoint
}

output "eks_kubeconfig_command" {
  description = "Run this to update your local kubeconfig"
  value       = "aws eks update-kubeconfig --region ${var.aws_region} --name ${aws_eks_cluster.main.name}"
}

# ── IAM Role ARNs for k8s ServiceAccount annotations ─────────────────────────

output "backend_pod_role_arn" {
  description = "Annotate the 'social-backend' ServiceAccount with this ARN for IRSA"
  value       = aws_iam_role.backend_pod.arn
}

output "alb_controller_role_arn" {
  description = "Annotate the 'aws-load-balancer-controller' ServiceAccount with this ARN"
  value       = aws_iam_role.alb_controller.arn
}

# ── Database Endpoints ────────────────────────────────────────────────────────

output "rds_endpoint" {
  description = "RDS PostgreSQL endpoint (use via PgBouncer in k8s)"
  value       = aws_db_instance.postgres.address
}

output "rds_secret_arn" {
  value = aws_secretsmanager_secret.postgres.arn
}

output "elasticache_primary_endpoint" {
  description = "Redis primary endpoint — use rediss://:AUTH@host:6379/0"
  value       = aws_elasticache_replication_group.redis.primary_endpoint_address
}

output "elasticache_reader_endpoint" {
  description = "Redis reader endpoint (round-robins across replicas)"
  value       = aws_elasticache_replication_group.redis.reader_endpoint_address
}

output "documentdb_endpoint" {
  description = "DocumentDB cluster endpoint (writer)"
  value       = aws_docdb_cluster.main.endpoint
}

output "documentdb_reader_endpoint" {
  value = aws_docdb_cluster.main.reader_endpoint
}

output "msk_bootstrap_brokers_sasl_scram" {
  description = "MSK SASL/SCRAM bootstrap brokers — set as KAFKA_BOOTSTRAP_SERVERS"
  value       = aws_msk_cluster.main.bootstrap_brokers_sasl_scram
}

# ── Storage ───────────────────────────────────────────────────────────────────

output "media_bucket_name" {
  value = aws_s3_bucket.media.bucket
}

output "backups_bucket_name" {
  value = aws_s3_bucket.backups.bucket
}

output "ecr_backend_url" {
  description = "Push backend images here: docker push <url>:v1.0.0"
  value       = aws_ecr_repository.backend.repository_url
}

output "ecr_frontend_url" {
  value = aws_ecr_repository.frontend.repository_url
}

# ── DNS ───────────────────────────────────────────────────────────────────────

output "route53_name_servers" {
  description = "Delegate your domain to these NS records at your registrar"
  value       = aws_route53_zone.main.name_servers
}

output "acm_certificate_arn" {
  value = aws_acm_certificate.main.arn
}
