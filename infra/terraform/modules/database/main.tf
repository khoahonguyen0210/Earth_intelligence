# RDS for PostgreSQL 16 (PostGIS ships with it; Flyway's V1 migration
# runs CREATE EXTENSION itself) -- docs/cloud-deployment.md "Database".

resource "aws_db_subnet_group" "this" {
  name       = var.name
  subnet_ids = var.subnet_ids
}

resource "aws_security_group" "this" {
  name        = "${var.name}-postgres"
  description = "PostgreSQL, reachable only from the EKS nodes"
  vpc_id      = var.vpc_id
}

# count, not for_each: the node security group ID is unknown until the
# cluster exists, and for_each keys must be known at plan time.
resource "aws_vpc_security_group_ingress_rule" "postgres" {
  count = length(var.allowed_security_group_ids)

  security_group_id            = aws_security_group.this.id
  referenced_security_group_id = var.allowed_security_group_ids[count.index]
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
}

resource "aws_db_instance" "this" {
  identifier = var.name

  engine         = "postgres"
  engine_version = "16"
  instance_class = var.instance_class

  allocated_storage     = 20
  max_allocated_storage = 50
  storage_type          = "gp3"
  storage_encrypted     = true

  # Same database/user names as every local stack (application.properties,
  # infra/k8s/configmap.yaml), so only the host and password change.
  db_name  = "ai_earth"
  username = "ai_earth"

  # RDS generates the password and keeps it in Secrets Manager; it never
  # appears in Terraform variables or state.
  manage_master_user_password = true

  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [aws_security_group.this.id]
  publicly_accessible    = false
  multi_az               = false

  backup_retention_period    = 7
  auto_minor_version_upgrade = true

  # The environment is brought up for runs and taken down with
  # `terraform destroy` (docs/cloud-deployment.md, cost section), so a
  # destroy must not stall on a final snapshot or deletion protection.
  # Consequence: destroy deletes every persisted result.
  skip_final_snapshot = true
  deletion_protection = false
}
