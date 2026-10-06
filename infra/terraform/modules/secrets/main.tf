resource "aws_secretsmanager_secret" "firms" {
  name        = "${var.project}/firms"
  description = "NASA FIRMS map key, JSON {\"map_key\": \"...\"} -> ai-earth-secret FIRMS_MAP_KEY"

  recovery_window_in_days = 0
}
