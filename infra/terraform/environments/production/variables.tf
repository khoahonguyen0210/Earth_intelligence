# Defaults are the locked values from docs/cloud-deployment.md (Task 12.1).
# Changing one of them reopens a locked decision; it is not tuning.

variable "region" {
  description = "AWS region for every resource in this environment."
  type        = string
  default     = "us-west-2"
}

variable "project" {
  description = "Name prefix for resources and the Project tag."
  type        = string
  default     = "ai-earth"
}

variable "environment" {
  description = "Environment name (the Environment tag)."
  type        = string
  default     = "production"
}

variable "vpc_cidr" {
  description = "CIDR block of the VPC."
  type        = string
  default     = "10.0.0.0/16"
}

variable "kubernetes_version" {
  description = "EKS Kubernetes minor version (in standard support until 2027-08-02)."
  type        = string
  default     = "1.36"
}

variable "node_instance_types" {
  description = "Instance types of the EKS managed node group."
  type        = list(string)
  default     = ["m6i.large"]
}

variable "node_min_size" {
  description = "Minimum node count (2 = one per AZ, not a capacity estimate)."
  type        = number
  default     = 2
}

variable "node_max_size" {
  description = "Maximum node count."
  type        = number
  default     = 4
}

variable "db_instance_class" {
  description = "RDS instance class."
  type        = string
  default     = "db.t4g.micro"
}

variable "cache_node_type" {
  description = "ElastiCache node type."
  type        = string
  default     = "cache.t4g.micro"
}

# Task 13.4: HTTPS (docs/security-baseline.md). No domain is locked, so
# both default to null and the certificate is created only once a domain
# is chosen; until then the ALB serves plain HTTP on its AWS DNS name.
variable "domain_name" {
  description = "Domain the product is served on over HTTPS; null for HTTP on the ALB's own name."
  type        = string
  default     = null
}

variable "route53_zone_id" {
  description = "Route 53 hosted zone of domain_name; null if its DNS is hosted elsewhere."
  type        = string
  default     = null
}
