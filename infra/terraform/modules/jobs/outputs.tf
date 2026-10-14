output "table_name" {
  value = aws_dynamodb_table.forecast_jobs.name
}

output "table_arn" {
  value = aws_dynamodb_table.forecast_jobs.arn
}
