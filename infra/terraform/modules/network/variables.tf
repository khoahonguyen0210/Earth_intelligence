variable "name" {
  description = "Name prefix for the VPC and its resources."
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR block of the VPC."
  type        = string
}
