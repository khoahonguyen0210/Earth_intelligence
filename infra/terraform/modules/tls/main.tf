# Task 13.4: the ALB's HTTPS certificate -- docs/security-baseline.md.
# An ACM certificate for the product's domain, validated over DNS. When
# the domain's zone is in Route 53 (route53_zone_id set), the validation
# records are created here and Terraform waits for issuance; otherwise
# the records are output for whoever runs that DNS to add by hand.
# ACM renews a DNS-validated certificate automatically as long as those
# records stay in place.

resource "aws_acm_certificate" "this" {
  domain_name       = var.domain_name
  validation_method = "DNS"

  # A replacement certificate must exist before the old one is detached
  # from the ALB's HTTPS listener.
  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_route53_record" "validation" {
  for_each = var.route53_zone_id == null ? {} : {
    for option in aws_acm_certificate.this.domain_validation_options : option.domain_name => option
  }

  zone_id         = var.route53_zone_id
  name            = each.value.resource_record_name
  type            = each.value.resource_record_type
  records         = [each.value.resource_record_value]
  ttl             = 60
  allow_overwrite = true
}

resource "aws_acm_certificate_validation" "this" {
  count = var.route53_zone_id == null ? 0 : 1

  certificate_arn         = aws_acm_certificate.this.arn
  validation_record_fqdns = [for record in aws_route53_record.validation : record.fqdn]
}
