variable "name" {
  description = "Identifier prefix for the instance and its resources."
  type        = string
}

variable "vpc_id" {
  description = "VPC of the security group."
  type        = string
}

variable "subnet_ids" {
  description = "Private subnets for the DB subnet group."
  type        = list(string)
}

variable "allowed_security_group_ids" {
  description = "Security groups allowed to connect on 5432."
  type        = list(string)
}

variable "instance_class" {
  description = "RDS instance class."
  type        = string
}
