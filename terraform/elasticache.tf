resource "aws_elasticache_subnet_group" "main" {
  name       = local.name
  subnet_ids = aws_subnet.database[*].id
  tags       = { Name = "${local.name}-elasticache-subnet-group" }
}

resource "aws_elasticache_parameter_group" "redis" {
  name   = "${local.name}-redis7"
  family = "redis7"

  parameter {
    name  = "maxmemory-policy"
    value = "allkeys-lru"
  }
}

# Replication group: 1 primary + 2 replicas, mirroring the Redis Sentinel
# setup in k8s/22-redis.yaml. ElastiCache handles automatic failover.
# App connection string format (TLS + AUTH):
#   rediss://:${auth_token}@${primary_endpoint}:6379/0
resource "aws_elasticache_replication_group" "redis" {
  replication_group_id = local.name
  description          = "Social app Redis - presence, feed cache, rate limiting, pub/sub"

  node_type            = var.elasticache_node_type
  num_cache_clusters   = 3
  parameter_group_name = aws_elasticache_parameter_group.redis.name
  subnet_group_name    = aws_elasticache_subnet_group.main.name
  security_group_ids   = [aws_security_group.elasticache.id]

  engine_version = "7.1"
  port           = 6379

  # Encryption required to use AUTH token
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  auth_token                 = var.elasticache_auth_token

  automatic_failover_enabled = true
  multi_az_enabled           = true

  snapshot_retention_limit = 3
  snapshot_window          = "03:00-04:00"
  maintenance_window       = "Mon:04:00-Mon:05:00"

  tags = { Name = "${local.name}-redis" }
}
