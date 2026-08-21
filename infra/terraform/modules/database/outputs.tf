output "endpoint" {
  description = "host:port of the instance."
  value       = aws_db_instance.this.endpoint
}

output "db_name" {
  value = aws_db_instance.this.db_name
}

output "username" {
  value = aws_db_instance.this.username
}

output "master_user_secret_arn" {
  description = "RDS-managed Secrets Manager secret with the master password."
  value       = aws_db_instance.this.master_user_secret[0].secret_arn
}
