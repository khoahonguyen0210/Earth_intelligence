# The FIRMS map key's Secrets Manager container -- docs/cloud-deployment.md
# "Secrets". Terraform creates the secret but never its value: the key is
# written out of band (docs/terraform-layout.md), so it never enters
# Terraform variables or state. The DB password secret is not here; RDS
# creates and rotates that one itself (modules/database).

resource "aws_secretsmanager_secret" "firms" {
  name        = "${var.project}/firms"
  description = "NASA FIRMS map key, JSON {\"map_key\": \"...\"} -> ai-earth-secret FIRMS_MAP_KEY"

  # Delete immediately on destroy instead of the default 30-day recovery
  # window, which would block re-creating the same name on the next
  # bring-up. Consequence: the value must be written again after each
  # destroy/apply cycle.
  recovery_window_in_days = 0
}
