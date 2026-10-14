variable "table_name" {
  description = "Name of the forecast job table."
  type        = string
}

variable "deletion_protection" {
  description = "Block deleting the table outside Terraform."
  type        = bool
  default     = true
}
