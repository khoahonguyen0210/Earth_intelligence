output "repository_urls" {
  description = "Repository name -> push/pull URL."
  value       = { for name, repo in aws_ecr_repository.this : name => repo.repository_url }
}
