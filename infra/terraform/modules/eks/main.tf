# EKS 1.36 control plane, one managed node group, and the AWS-managed /
# community EKS add-ons -- docs/cloud-deployment.md "Kubernetes". Helm-
# installed controllers live in modules/platform instead.

locals {
  # The CloudWatch Observability add-on writes container logs into these
  # four groups. Creating them here first is the only way to give them a
  # retention period -- groups the add-on creates itself never expire.
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

  # Public API endpoint so terraform's helm provider and kubectl can reach
  # the cluster from outside the VPC; nodes use the private endpoint.
  endpoint_public_access  = true
  endpoint_private_access = true

  # Access entries only (no aws-auth ConfigMap), and the identity running
  # terraform becomes cluster admin -- required for the helm releases
  # applied by this same run.
  authentication_mode                      = "API"
  enable_cluster_creator_admin_permissions = true

  # Pod Identity is the chosen pod IAM mechanism, so no OIDC provider.
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
    # Community add-on (AWS validates version compatibility only).
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

# Named from var.name (the cluster name), not module.eks.cluster_name, so
# these are created while the ~10-minute control plane is still coming up
# -- long before the add-on starts shipping logs and would otherwise
# create the groups itself, which would make this create fail on "already
# exists".
resource "aws_cloudwatch_log_group" "container_insights" {
  for_each = toset(local.container_insights_log_groups)

  name              = "/aws/containerinsights/${var.name}/${each.key}"
  retention_in_days = var.log_retention_days
}
