variable "bucket_name" {
  description = "Globally unique bucket name."
  type        = string
}

variable "noncurrent_version_days" {
  description = "Days to keep overwritten object versions before they expire."
  type        = number
  default     = 90
}
