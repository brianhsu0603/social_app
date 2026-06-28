# ── EKS ──────────────────────────────────────────────────────────────────────

resource "aws_security_group" "eks_cluster" {
  name        = "${local.name}-eks-cluster"
  description = "EKS control plane"
  vpc_id      = aws_vpc.main.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${local.name}-eks-cluster-sg" }
}

resource "aws_security_group" "eks_nodes" {
  name        = "${local.name}-eks-nodes"
  description = "EKS worker nodes"
  vpc_id      = aws_vpc.main.id

  # Node-to-node (pod networking, kubelet, etc.)
  ingress {
    from_port = 0
    to_port   = 0
    protocol  = "-1"
    self      = true
  }

  # Control plane → nodes (webhooks, exec)
  ingress {
    from_port       = 1025
    to_port         = 65535
    protocol        = "tcp"
    security_groups = [aws_security_group.eks_cluster.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${local.name}-eks-nodes-sg" }
}

# Allow control plane to reach nodes
resource "aws_security_group_rule" "cluster_to_nodes_ephemeral" {
  type                     = "egress"
  from_port                = 1025
  to_port                  = 65535
  protocol                 = "tcp"
  security_group_id        = aws_security_group.eks_cluster.id
  source_security_group_id = aws_security_group.eks_nodes.id
}

# Allow nodes to talk to the API server
resource "aws_security_group_rule" "nodes_to_cluster_443" {
  type                     = "ingress"
  from_port                = 443
  to_port                  = 443
  protocol                 = "tcp"
  security_group_id        = aws_security_group.eks_cluster.id
  source_security_group_id = aws_security_group.eks_nodes.id
}

# ── RDS PostgreSQL ────────────────────────────────────────────────────────────

resource "aws_security_group" "rds" {
  name        = "${local.name}-rds"
  description = "RDS PostgreSQL - EKS nodes only"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.eks_nodes.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${local.name}-rds-sg" }
}

# ── ElastiCache Redis ─────────────────────────────────────────────────────────

resource "aws_security_group" "elasticache" {
  name        = "${local.name}-elasticache"
  description = "ElastiCache Redis - EKS nodes only"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_security_group.eks_nodes.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${local.name}-elasticache-sg" }
}

# ── DocumentDB ────────────────────────────────────────────────────────────────

resource "aws_security_group" "documentdb" {
  name        = "${local.name}-documentdb"
  description = "DocumentDB - EKS nodes only"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port       = 27017
    to_port         = 27017
    protocol        = "tcp"
    security_groups = [aws_security_group.eks_nodes.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${local.name}-documentdb-sg" }
}

# ── MSK Kafka ─────────────────────────────────────────────────────────────────

resource "aws_security_group" "msk" {
  name        = "${local.name}-msk"
  description = "MSK Kafka - EKS nodes only"
  vpc_id      = aws_vpc.main.id

  # SASL/SCRAM + TLS (port 9096)
  ingress {
    from_port       = 9096
    to_port         = 9096
    protocol        = "tcp"
    security_groups = [aws_security_group.eks_nodes.id]
    description     = "SASL/SCRAM client"
  }

  # Broker-to-broker replication (self)
  ingress {
    from_port = 9094
    to_port   = 9094
    protocol  = "tcp"
    self      = true
    description = "Broker replication"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${local.name}-msk-sg" }
}
