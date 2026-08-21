variable "repository_names" {
  description = "ECR repositories to create."
  type        = list(string)
}

variable "images_to_keep" {
  description = "Images retained per repository by the lifecycle policy."
  type        = number
  default     = 10
}
