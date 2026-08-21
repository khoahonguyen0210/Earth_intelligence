variable "name" {
  description = "Cluster name."
  type        = string
}

variable "kubernetes_version" {
  description = "EKS Kubernetes minor version."
  type        = string
}

variable "vpc_id" {
  description = "VPC the cluster runs in."
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnets for the control plane ENIs and the nodes."
  type        = list(string)
}

variable "node_instance_types" {
  description = "Instance types of the managed node group."
  type        = list(string)
}

variable "node_min_size" {
  description = "Minimum (and initial) node count."
  type        = number
}

variable "node_max_size" {
  description = "Maximum node count."
  type        = number
}

variable "log_retention_days" {
  description = "Retention of control-plane and container log groups."
  type        = number
  default     = 30
}
