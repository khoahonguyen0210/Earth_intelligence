variable "name" {
  description = "Replication group ID and resource name prefix."
  type        = string
}

variable "vpc_id" {
  description = "VPC of the security group."
  type        = string
}

variable "subnet_ids" {
  description = "Private subnets for the cache subnet group."
  type        = list(string)
}

variable "allowed_security_group_ids" {
  description = "Security groups allowed to connect on 6379."
  type        = list(string)
}

variable "node_type" {
  description = "ElastiCache node type."
  type        = string
}
