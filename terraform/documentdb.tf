# DocumentDB is MongoDB-compatible (API subset). This app uses Motor (async
# MongoDB driver) for messages and read receipts, both of which are fully
# supported. Notable gap: DocumentDB does not support the $text full-text
# search operator — search is handled by Meilisearch, so this is not an issue.
#
# Connection string for the app:
#   mongodb://${username}:${password}@${cluster_endpoint}:27017/?tls=true&tlsCAFile=/etc/ssl/certs/rds-combined-ca-bundle.pem&replicaSet=rs0&readPreference=secondaryPreferred
# Download the CA bundle once into the container image:
#   curl -O https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem

resource "aws_docdb_subnet_group" "main" {
  name       = local.name
  subnet_ids = aws_subnet.database[*].id
  tags       = { Name = "${local.name}-docdb-subnet-group" }
}

resource "aws_docdb_cluster_parameter_group" "main" {
  name   = local.name
  family = "docdb5.0"

  parameter {
    name  = "tls"
    value = "enabled"
  }

  parameter {
    name  = "audit_logs"
    value = "disabled"
  }
}

resource "aws_docdb_cluster" "main" {
  cluster_identifier = local.name

  engine         = "docdb"
  engine_version = "5.0.0"

  master_username = var.docdb_username
  master_password = var.docdb_password

  db_subnet_group_name            = aws_docdb_subnet_group.main.name
  vpc_security_group_ids          = [aws_security_group.documentdb.id]
  db_cluster_parameter_group_name = aws_docdb_cluster_parameter_group.main.name

  storage_encrypted = true

  backup_retention_period = 7
  preferred_backup_window = "03:30-04:30"
  preferred_maintenance_window = "Mon:05:00-Mon:06:00"

  deletion_protection     = true
  skip_final_snapshot     = false
  final_snapshot_identifier = "${local.name}-docdb-final"

  enabled_cloudwatch_logs_exports = ["audit", "profiler"]

  tags = { Name = "${local.name}-docdb" }
}

# 1 primary + 2 replicas across AZs (same topology as the k8s StatefulSet)
resource "aws_docdb_cluster_instance" "main" {
  count              = 3
  identifier         = "${local.name}-docdb-${count.index}"
  cluster_identifier = aws_docdb_cluster.main.id
  instance_class     = var.docdb_instance_class

  auto_minor_version_upgrade = true

  tags = { Name = "${local.name}-docdb-${count.index}" }
}
