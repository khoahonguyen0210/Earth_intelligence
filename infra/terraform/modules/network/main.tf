# VPC, 2 AZs, public + private subnets, one NAT gateway, and a free S3
# gateway endpoint -- docs/cloud-deployment.md "Networking".

data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  azs = slice(data.aws_availability_zones.available.names, 0, 2)
}

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "6.7.3"

  name = var.name
  cidr = var.vpc_cidr
  azs  = local.azs

  # /20 private subnets leave room for VPC CNI's one-IP-per-pod model; the
  # public subnets only ever hold the ALB and the NAT gateway.
  private_subnets = [for i, _ in local.azs : cidrsubnet(var.vpc_cidr, 4, i)]
  public_subnets  = [for i, _ in local.azs : cidrsubnet(var.vpc_cidr, 8, 48 + i)]

  # One NAT gateway, not one per AZ: an accepted single-AZ egress risk for
  # half the fixed NAT cost.
  enable_nat_gateway = true
  single_nat_gateway = true

  enable_dns_hostnames = true
  enable_dns_support   = true

  # Subnet discovery tags the AWS Load Balancer Controller uses to place
  # the internet-facing ALB (public) and any internal load balancer
  # (private).
  public_subnet_tags = {
    "kubernetes.io/role/elb" = "1"
  }
  private_subnet_tags = {
    "kubernetes.io/role/internal-elb" = "1"
  }
}

# Keeps the backend's artifact reads/writes off the NAT gateway's per-GB
# processing charge.
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = module.vpc.vpc_id
  service_name      = "com.amazonaws.${data.aws_region.current.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = module.vpc.private_route_table_ids

  tags = {
    Name = "${var.name}-s3"
  }
}

data "aws_region" "current" {}
