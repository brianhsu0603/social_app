# All secrets are stored in Secrets Manager under the ${local.name}/ prefix.
# The backend pod IRSA role has GetSecretValue on this prefix.
# In the k8s manifests, replace the plain Secret with an ExternalSecret
# (External Secrets Operator) pointing at these ARNs.

resource "aws_secretsmanager_secret" "postgres" {
  name                    = "${local.name}/postgres"
  description             = "RDS PostgreSQL credentials"
  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret_version" "postgres" {
  secret_id = aws_secretsmanager_secret.postgres.id
  secret_string = jsonencode({
    username = var.rds_username
    password = var.rds_password
    host     = aws_db_instance.postgres.address
    port     = 5432
    dbname   = "social"
    url      = "postgresql+psycopg://${var.rds_username}:${var.rds_password}@${aws_db_instance.postgres.address}:5432/social"
  })
}

resource "aws_secretsmanager_secret" "redis" {
  name                    = "${local.name}/redis"
  description             = "ElastiCache Redis connection details"
  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret_version" "redis" {
  secret_id = aws_secretsmanager_secret.redis.id
  secret_string = jsonencode({
    auth_token       = var.elasticache_auth_token
    primary_endpoint = aws_elasticache_replication_group.redis.primary_endpoint_address
    reader_endpoint  = aws_elasticache_replication_group.redis.reader_endpoint_address
    url              = "rediss://:${var.elasticache_auth_token}@${aws_elasticache_replication_group.redis.primary_endpoint_address}:6379/0"
  })
}

resource "aws_secretsmanager_secret" "documentdb" {
  name                    = "${local.name}/documentdb"
  description             = "DocumentDB (MongoDB-compatible) credentials"
  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret_version" "documentdb" {
  secret_id = aws_secretsmanager_secret.documentdb.id
  secret_string = jsonencode({
    username = var.docdb_username
    password = var.docdb_password
    endpoint = aws_docdb_cluster.main.endpoint
    url      = "mongodb://${var.docdb_username}:${var.docdb_password}@${aws_docdb_cluster.main.endpoint}:27017/?tls=true&replicaSet=rs0&readPreference=secondaryPreferred"
  })
}

# MSK requires a customer-managed KMS key (not the AWS managed alias)
resource "aws_kms_key" "msk" {
  description             = "KMS key for MSK SCRAM secret"
  deletion_window_in_days = 7
}

# MSK SCRAM secret must follow the AmazonMSK_-prefixed naming convention
resource "aws_secretsmanager_secret" "msk" {
  name                    = "AmazonMSK_${local.name}"
  description             = "MSK SASL/SCRAM credentials"
  recovery_window_in_days = 7
  kms_key_id              = aws_kms_key.msk.key_id
}

resource "aws_secretsmanager_secret_version" "msk" {
  secret_id = aws_secretsmanager_secret.msk.id
  secret_string = jsonencode({
    username = var.msk_username
    password = var.msk_password
  })
}

# App-level secrets (JWT key, push creds, Meilisearch master key, etc.)
# Populate these values after initial apply.
resource "aws_secretsmanager_secret" "app" {
  name                    = "${local.name}/app"
  description             = "Application secrets (JWT, push creds, Meili key)"
  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret_version" "app" {
  secret_id = aws_secretsmanager_secret.app.id
  secret_string = jsonencode({
    SECRET_KEY       = "REPLACE_ME"
    MEILI_MASTER_KEY = "REPLACE_ME"
    FCM_PROJECT_ID   = ""
    FCM_ACCESS_TOKEN = ""
    APNS_JWT         = ""
    APNS_BUNDLE_ID   = ""
  })
}
