output "certificate_arn" {
  description = "For the Ingress annotation alb.ingress.kubernetes.io/certificate-arn."
  value = var.route53_zone_id == null ? aws_acm_certificate.this.arn : aws_acm_certificate_validation.this[0].certificate_arn
}

output "validation_records" {
  description = "DNS records that prove domain ownership, when the zone is not in Route 53."
  value = [
    for option in aws_acm_certificate.this.domain_validation_options : {
      name  = option.resource_record_name
      type  = option.resource_record_type
      value = option.resource_record_value
    }
  ]
}
