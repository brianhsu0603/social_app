# MSK replaces Strimzi Kafka (k8s/23-kafka.yaml). 3 brokers, one per AZ.
#
# The app's aiokafka client must be updated to use SASL/SCRAM + TLS:
#   AIOKafkaProducer(
#     bootstrap_servers=settings.kafka_bootstrap_servers,
#     security_protocol="SASL_SSL",
#     sasl_mechanism="SCRAM-SHA-512",
#     sasl_plain_username=settings.kafka_username,
#     sasl_plain_password=settings.kafka_password,
#     ...
#   )
# Add KAFKA_USERNAME and KAFKA_PASSWORD to the k8s ConfigMap/Secret.

resource "aws_msk_configuration" "main" {
  name           = local.name
  kafka_versions = ["3.6.0"]

  server_properties = <<-EOF
    auto.create.topics.enable=false
    default.replication.factor=3
    min.insync.replicas=2
    num.partitions=12
    log.retention.hours=168
    log.segment.bytes=1073741824
    compression.type=gzip
    unclean.leader.election.enable=false
  EOF
}

resource "aws_msk_cluster" "main" {
  cluster_name           = local.name
  kafka_version          = "3.6.0"
  number_of_broker_nodes = 3

  broker_node_group_info {
    instance_type  = var.msk_instance_type
    client_subnets = aws_subnet.database[*].id
    security_groups = [aws_security_group.msk.id]

    storage_info {
      ebs_storage_info {
        volume_size = var.msk_ebs_volume_size
      }
    }
  }

  configuration_info {
    arn      = aws_msk_configuration.main.arn
    revision = aws_msk_configuration.main.latest_revision
  }

  client_authentication {
    sasl {
      scram = true
    }
    unauthenticated = false
  }

  encryption_info {
    encryption_in_transit {
      client_broker = "TLS"
      in_cluster    = true
    }
  }

  enhanced_monitoring = "PER_TOPIC_PER_BROKER"

  open_monitoring {
    prometheus {
      jmx_exporter  { enabled_in_broker = true }
      node_exporter { enabled_in_broker = true }
    }
  }

  tags = { Name = "${local.name}-kafka" }
}

# Associate the SCRAM credentials secret with the MSK cluster
resource "aws_msk_scram_secret_association" "main" {
  cluster_arn     = aws_msk_cluster.main.arn
  secret_arn_list = [aws_secretsmanager_secret.msk.arn]
  depends_on      = [aws_secretsmanager_secret_version.msk]
}
