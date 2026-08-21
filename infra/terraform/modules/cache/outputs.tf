output "primary_endpoint" {
  description = "Hostname of the primary node (TLS on port 6379)."
  value       = aws_elasticache_replication_group.this.primary_endpoint_address
}
