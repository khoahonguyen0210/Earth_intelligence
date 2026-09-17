data "aws_caller_identity" "current" {}

locals {
  name = "${var.project}-${var.environment}"

  # Service account the backend Deployment runs as in the cloud
  # manifests; its Pod Identity role is scoped to the artifact
  # bucket only.
  backend_namespace       = "default"
  backend_service_account = "backend"
}

module "network" {
  source = "../../modules/network"

  name     = local.name
  vpc_cidr = var.vpc_cidr
}

module "eks" {
  source = "../../modules/eks"

  name                = local.name
  kubernetes_version  = var.kubernetes_version
  vpc_id              = module.network.vpc_id
  private_subnet_ids  = module.network.private_subnet_ids
  node_instance_types = var.node_instance_types
  node_min_size       = var.node_min_size
  node_max_size       = var.node_max_size
}

module "database" {
  source = "../../modules/database"

  name                       = local.name
  vpc_id                     = module.network.vpc_id
  subnet_ids                 = module.network.private_subnet_ids
  allowed_security_group_ids = [module.eks.node_security_group_id]
  instance_class             = var.db_instance_class
}

module "cache" {
  source = "../../modules/cache"

  name                       = local.name
  vpc_id                     = module.network.vpc_id
  subnet_ids                 = module.network.private_subnet_ids
  allowed_security_group_ids = [module.eks.node_security_group_id]
  node_type                  = var.cache_node_type
}

module "storage" {
  source = "../../modules/storage"

  bucket_name = "${var.project}-artifacts-${data.aws_caller_identity.current.account_id}"
}

module "registry" {
  source = "../../modules/registry"

  repository_names = ["${var.project}-backend", "${var.project}-frontend"]
}

module "tls" {
  source = "../../modules/tls"
  count  = var.domain_name == null ? 0 : 1

  domain_name     = var.domain_name
  route53_zone_id = var.route53_zone_id
}

module "secrets" {
  source = "../../modules/secrets"

  project = var.project
}

module "platform" {
  source = "../../modules/platform"

  cluster_name = module.eks.cluster_name
  region       = var.region
  vpc_id       = module.network.vpc_id

  # External Secrets may read exactly these two secrets, nothing else.
  readable_secret_arns = [
    module.database.master_user_secret_arn,
    module.secrets.firms_secret_arn,
  ]

  backend_namespace       = local.backend_namespace
  backend_service_account = local.backend_service_account
  artifact_bucket_arn     = module.storage.bucket_arn

  # Helm releases need running nodes, not just a control plane.
  depends_on = [module.eks]
}
