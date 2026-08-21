# ElastiCache Redis OSS 7.1, one node, TLS in transit -- docs/cloud-
# deployment.md "Redis". A replication group rather than a plain cache
# cluster because in-transit encryption for Redis OSS needs one; with
# num_cache_clusters = 1 it is still a single node, no replica.

resource "aws_elasticache_subnet_group" "this" {
  name       = var.name
  subnet_ids = var.subnet_ids
}

resource "aws_security_group" "this" {
  name        = "${var.name}-redis"
  description = "Redis, reachable only from the EKS nodes"
  vpc_id      = var.vpc_id
}

# count, not for_each: see modules/database -- the node security group ID
# is unknown at plan time.
resource "aws_vpc_security_group_ingress_rule" "redis" {
  count = length(var.allowed_security_group_ids)

  security_group_id            = aws_security_group.this.id
  referenced_security_group_id = var.allowed_security_group_ids[count.index]
  ip_protocol                  = "tcp"
  from_port                    = 6379
  to_port                      = 6379
}

resource "aws_elasticache_replication_group" "this" {
  replication_group_id = var.name
  description          = "Forecast job queue (Task 6.5 RedisForecastQueue)"

  engine               = "redis"
  engine_version       = "7.1"
  parameter_group_name = "default.redis7"
  node_type            = var.node_type
  port                 = 6379

  num_cache_clusters         = 1
  automatic_failover_enabled = false
  multi_az_enabled           = false

  transit_encryption_enabled = true
  at_rest_encryption_enabled = true

  subnet_group_name  = aws_elasticache_subnet_group.this.name
  security_group_ids = [aws_security_group.this.id]

  # The queue holds only in-flight job ids (job state lives in Postgres),
  # so backups would restore stale ids, not useful state.
  snapshot_retention_limit = 0
}
