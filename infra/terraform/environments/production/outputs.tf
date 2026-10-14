output "region" {
  value = var.region
}

output "cluster_name" {
  value = module.eks.cluster_name
}

output "kubeconfig_command" {
  description = "Points local kubectl at the new cluster."
  value       = "aws eks update-kubeconfig --name ${module.eks.cluster_name} --region ${var.region}"
}

output "spring_datasource_url" {
  description = "ConfigMap SPRING_DATASOURCE_URL."
  value       = "jdbc:postgresql://${module.database.endpoint}/${module.database.db_name}"
}

output "postgres_user" {
  description = "ConfigMap POSTGRES_USER."
  value       = module.database.username
}

output "db_master_user_secret_arn" {
  description = "RDS-managed secret holding POSTGRES_PASSWORD (JSON key: password)."
  value       = module.database.master_user_secret_arn
}

output "redis_host" {
  description = "ConfigMap REDIS_HOST and the KEDA redis trigger address (TLS, port 6379)."
  value       = module.cache.primary_endpoint
}

output "object_store_bucket" {
  description = "ConfigMap OBJECT_STORE_BUCKET."
  value       = module.storage.bucket_name
}

output "firms_secret_arn" {
  description = "Secret holding FIRMS_MAP_KEY (JSON key: map_key); its value is set out of band."
  value       = module.secrets.firms_secret_arn
}

output "ecr_repository_urls" {
  value = module.registry.repository_urls
}

output "backend_service_account" {
  description = "Namespace/name the backend Deployment must run as to get S3 access."
  value       = "${local.backend_namespace}/${local.backend_service_account}"
}

output "certificate_arn" {
  description = "Ingress alb.ingress.kubernetes.io/certificate-arn; null until domain_name is set."
  value       = one(module.tls[*].certificate_arn)
}

output "certificate_validation_records" {
  description = "DNS records to add by hand when domain_name's zone is not in Route 53."
  value       = one(module.tls[*].validation_records)
}

output "forecast_job_table" {
  description = "DynamoDB table for forecast job status (FORECAST_JOBS_TABLE)."
  value       = module.jobs.table_name
}
