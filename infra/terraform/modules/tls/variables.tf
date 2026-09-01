variable "domain_name" {
  description = "Fully qualified domain name the product is served on, e.g. earth.example.org."
  type        = string
}

variable "route53_zone_id" {
  description = "Route 53 hosted zone of domain_name; null when its DNS is hosted elsewhere."
  type        = string
  default     = null
}
