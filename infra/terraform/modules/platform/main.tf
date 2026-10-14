locals {
  lb_controller_namespace       = "kube-system"
  lb_controller_service_account = "aws-load-balancer-controller"

  external_secrets_namespace       = "external-secrets"
  external_secrets_service_account = "external-secrets"
}

module "lb_controller_pod_identity" {
  source  = "terraform-aws-modules/eks-pod-identity/aws"
  version = "2.9.0"

  name = "${var.cluster_name}-aws-lb-controller"

  attach_aws_lb_controller_policy = true

  associations = {
    this = {
      cluster_name    = var.cluster_name
      namespace       = local.lb_controller_namespace
      service_account = local.lb_controller_service_account
    }
  }
}

module "external_secrets_pod_identity" {
  source  = "terraform-aws-modules/eks-pod-identity/aws"
  version = "2.9.0"

  name = "${var.cluster_name}-external-secrets"

  attach_external_secrets_policy        = true
  external_secrets_secrets_manager_arns = var.readable_secret_arns
  external_secrets_create_permission    = false

  associations = {
    this = {
      cluster_name    = var.cluster_name
      namespace       = local.external_secrets_namespace
      service_account = local.external_secrets_service_account
    }
  }
}

module "backend_pod_identity" {
  source  = "terraform-aws-modules/eks-pod-identity/aws"
  version = "2.9.0"

  name = "${var.cluster_name}-backend"

  attach_custom_policy = true
  policy_statements = [
    {
      sid       = "ArtifactBucket"
      actions   = ["s3:ListBucket"]
      resources = [var.artifact_bucket_arn]
    },
    {
      sid       = "ArtifactObjects"
      actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
      resources = ["${var.artifact_bucket_arn}/*"]
    },
    {
      sid = "ForecastJobTable"
      actions = [
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
        "dynamodb:Query",
        "dynamodb:DescribeTable",
        "dynamodb:ConditionCheckItem",
      ]
      resources = [var.job_table_arn, "${var.job_table_arn}/index/*"]
    },
  ]

  associations = {
    this = {
      cluster_name    = var.cluster_name
      namespace       = var.backend_namespace
      service_account = var.backend_service_account
    }
  }
}

resource "helm_release" "aws_load_balancer_controller" {
  name       = "aws-load-balancer-controller"
  namespace  = local.lb_controller_namespace
  repository = "https://aws.github.io/eks-charts"
  chart      = "aws-load-balancer-controller"
  version    = "3.5.0"

  values = [yamlencode({
    clusterName = var.cluster_name
    region      = var.region
    vpcId       = var.vpc_id
    serviceAccount = {
      create = true
      name   = local.lb_controller_service_account
    }
  })]

  depends_on = [module.lb_controller_pod_identity]
}

resource "helm_release" "keda" {
  name             = "keda"
  namespace        = "keda"
  create_namespace = true
  repository       = "https://kedacore.github.io/charts"
  chart            = "keda"
  version          = "2.21.0"

  depends_on = [helm_release.aws_load_balancer_controller]
}

resource "helm_release" "external_secrets" {
  name             = "external-secrets"
  namespace        = local.external_secrets_namespace
  create_namespace = true
  repository       = "https://charts.external-secrets.io"
  chart            = "external-secrets"
  version          = "2.11.0"

  values = [yamlencode({
    serviceAccount = {
      name = local.external_secrets_service_account
    }
  })]

  depends_on = [
    helm_release.aws_load_balancer_controller,
    module.external_secrets_pod_identity,
  ]
}

resource "helm_release" "reloader" {
  name             = "reloader"
  namespace        = "reloader"
  create_namespace = true
  repository       = "https://stakater.github.io/stakater-charts"
  chart            = "reloader"
  version          = "2.2.17"

  depends_on = [helm_release.aws_load_balancer_controller]
}
