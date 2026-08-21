output "firms_secret_arn" {
  value = aws_secretsmanager_secret.firms.arn
}

output "firms_secret_name" {
  value = aws_secretsmanager_secret.firms.name
}
