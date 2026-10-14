variable "cluster_name" {
  description = "EKS cluster the controllers and Pod Identity associations belong to."
  type        = string
}

variable "region" {
  description = "AWS region (the load balancer controller needs it explicitly)."
  type        = string
}

variable "vpc_id" {
  description = "VPC of the cluster (the load balancer controller needs it explicitly)."
  type        = string
}

variable "readable_secret_arns" {
  description = "Secrets Manager secrets External Secrets may read."
  type        = list(string)
}

variable "artifact_bucket_arn" {
  description = "The one S3 bucket the backend may read and write."
  type        = string
}

variable "job_table_arn" {
  description = "The DynamoDB forecast job table the backend may read and write."
  type        = string
}

variable "backend_namespace" {
  description = "Namespace of the backend service account."
  type        = string
}

variable "backend_service_account" {
  description = "Name of the backend service account."
  type        = string
}
