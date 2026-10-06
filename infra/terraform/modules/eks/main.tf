locals {
  container_insights_log_groups = ["application", "dataplane", "host", "performance"]
}

module "cloudwatch_observability_pod_identity" {
  source  = "terraform-aws-modules/eks-pod-identity/aws"
  version = "2.9.0"

  name = "${var.name}-cloudwatch-observability"

  attach_aws_cloudwatch_observability_policy = true
}

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "21.26.0"

  name               = var.name
  kubernetes_version = var.kubernetes_version

  vpc_id     = var.vpc_id
  subnet_ids = var.private_subnet_ids

  endpoint_public_access  = true
  endpoint_private_access = true

  authentication_mode                      = "API"
  enable_cluster_creator_admin_permissions = true

  enable_irsa = false

  cloudwatch_log_group_retention_in_days = var.log_retention_days

  addons = {
    vpc-cni = {
      before_compute = true
    }
    eks-pod-identity-agent = {
      before_compute = true
    }
    kube-proxy = {}
    coredns    = {}
    metrics-server = {}
    amazon-cloudwatch-observability = {
      pod_identity_association = [{
        role_arn        = module.cloudwatch_observability_pod_identity.iam_role_arn
        service_account = "cloudwatch-agent"
      }]
    }
  }

  eks_managed_node_groups = {
    default = {
      instance_types = var.node_instance_types
      min_size       = var.node_min_size
      max_size       = var.node_max_size
      desired_size   = var.node_min_size
    }
  }
}

resource "aws_cloudwatch_log_group" "container_insights" {
  for_each = toset(local.container_insights_log_groups)

  name              = "/aws/containerinsights/${var.name}/${each.key}"
  retention_in_days = var.log_retention_days
}
