# Terraform Layout — LOCKED

This document freezes the Terraform layout. It is not a
brainstorming document. The code implements
exactly the deployment `docs/cloud-deployment.md` locked;
a later step runs `init`/`plan`/`apply` against it, and nothing here has
been applied yet.

## Status: written and validated, not applied

Provisioning, deploying, and the cloud benchmark are **deferred, not
done**. Running them needs a live AWS account and costs about
$0.40/hour while the environment is up (`docs/cloud-deployment.md`,
cost section), and the project owner chose not to take that on for now.
So, stated plainly:

```text
done       Terraform for the full locked deployment; fmt/validate/lock pass;
           Trivy static scan clean apart from one accepted finding
not done   terraform plan/apply against a real account; the cloud-manifest
           code gaps (S3 client, frontend API base URL, Redis TLS); any cloud
           measurement
```

No cloud runtime, throughput, or cost number exists for this project,
and none may be claimed. The local Kubernetes results
(`docs/kubernetes-benchmark.md`) are the latest measured deployment
results. Resuming later is exactly the steps below, starting
from the one-time state-bucket bootstrap; nothing here needs rewriting
first.

## Layout

The required tree, with one module per locked AWS concern:

```text
infra/terraform/
├── modules/
│   ├── network/    VPC, 2 AZs, public/private subnets, 1 NAT, S3 gateway endpoint
│   ├── eks/        EKS 1.36, managed node group, EKS add-ons, Container Insights log groups
│   ├── database/   RDS PostgreSQL 16, RDS-managed master password
│   ├── cache/      ElastiCache Redis OSS 7.1, 1 node, TLS
│   ├── storage/    the artifact bucket
│   ├── registry/   ECR: ai-earth-backend, ai-earth-frontend
│   ├── secrets/    the FIRMS map key secret (container only, no value)
│   └── platform/   Pod Identity roles + Helm: LB controller, KEDA, External Secrets, Reloader
└── environments/
    └── production/
        ├── versions.tf           Terraform/provider pins, S3 backend (partial)
        ├── providers.tf          aws (default tags), helm (exec token auth)
        ├── variables.tf          locked values as defaults
        ├── main.tf               wires the eight modules together
        ├── outputs.tf            every value the cloud manifests need
        ├── backend.hcl.example   state bucket name template (real file gitignored)
        └── .terraform.lock.hcl   provider hashes for windows/linux/darwin
```

`modules/` holds reusable pieces with no environment-specific values.
`environments/production/` is the only root module and the only place
the locked numbers (region, versions, sizes) appear. They are variable
defaults, so there is no `terraform.tfvars` to keep in sync.

## Reused, not rebuilt

Per the reuse policy, the VPC, EKS, and IAM-role
plumbing come from the community `terraform-aws-modules` rather than
being hand-written:

```text
source                                     version  license     used in          modifications
terraform-aws-modules/vpc/aws              6.7.3    Apache-2.0  modules/network  none (inputs only)
terraform-aws-modules/eks/aws              21.26.0  Apache-2.0  modules/eks      none (inputs only)
terraform-aws-modules/eks-pod-identity/aws 2.9.0    Apache-2.0  modules/eks,     none (inputs only)
                                                                modules/platform
```

`eks-pod-identity` also supplies the AWS Load Balancer Controller's,
External Secrets', and CloudWatch agent's published IAM policies
(`attach_*_policy`), so none of those long policy documents is copied
into this repository to drift out of date.

## Pinned versions

Each was the latest stable release when this was written, looked up
directly (Terraform Registry API, each chart's Helm index), not recalled:

```text
Terraform                     ~> 1.16   (validated on 1.16.4)
hashicorp/aws                 ~> 6.66   (locked 6.66.0)
hashicorp/helm                ~> 3.3    (locked 3.3.0)
aws-load-balancer-controller  3.5.0     chart
keda                          2.21.0    chart -- the only KEDA minor tested against
                                        Kubernetes 1.36 (keda.sh compatibility matrix);
                                        the local kind cluster's 2.17.1 is not
external-secrets              2.11.0    chart
reloader                      2.2.17    chart
```

EKS add-on versions (`vpc-cni`, `coredns`, `kube-proxy`,
`eks-pod-identity-agent`, `metrics-server`,
`amazon-cloudwatch-observability`) are **not** pinned: the EKS module's
default `most_recent = true` resolves the newest version AWS publishes
as compatible with the cluster's 1.36 at apply time. Pinning them would
require querying `aws eks describe-addon-versions` against a real
account, and a real account is not available until the environment is
actually provisioned. That is also where the CloudWatch add-on's
>= v3.1.0 requirement for Pod Identity is confirmed, not assumed.

## Decisions the code had to make that the deployment design did not

**One root, Helm provider included.** The Helm provider authenticates
with `aws eks get-token` (an exec plugin), against the cluster this same
root creates. The alternative, a second root for in-cluster components,
means two applies, two states, and remote-state wiring between them.
One root works because the token is fetched only when a release is
actually applied, after the cluster exists. `module.platform` has
`depends_on = [module.eks]`, so the releases wait for the node group,
not just the control plane.

**Helm install order.** KEDA, External Secrets and Reloader all
`depends_on` the load balancer controller release. Its mutating webhook
intercepts every Service creation, and a chart that creates a Service
before the webhook is serving fails to install.

**Cluster access.** Access entries only (`authentication_mode = "API"`,
no `aws-auth` ConfigMap), and the identity running `terraform apply`
becomes cluster admin (`enable_cluster_creator_admin_permissions`). The
Helm releases in the same run need that. The public API endpoint stays
on so Terraform and `kubectl` can reach the cluster from outside the
VPC. `enable_irsa = false`, because Pod Identity is the chosen mechanism
and IRSA's OIDC provider would be unused.

**Log retention actually applied.** The CloudWatch Observability add-on
creates `/aws/containerinsights/<cluster>/{application,dataplane,host,performance}`
with no expiry if they do not exist yet. `modules/eks` pre-creates all
four with 30-day retention, naming them from the cluster name input
rather than the cluster resource. That way they exist minutes before the
add-on could create them first, which would make Terraform's create fail
on "already exists". The control-plane log group gets the same 30 days.

**ElastiCache replication group, not a plain cache cluster.** Redis OSS
in-transit encryption requires a replication group. `num_cache_clusters
= 1` keeps it the single node already locked. Snapshots are off,
because the queue only holds in-flight job ids and job state lives in
Postgres.

**Security group rules use `count`, not `for_each`.** The node security
group ID is unknown until the cluster exists, and `for_each` keys must
be known at plan time.

**Immutable ECR tags.** A pushed tag can never be overwritten, so a
running deployment's image cannot change underneath it. The cloud
manifests therefore tag each push with the git commit SHA, never a
reused `latest`.

**Teardown is a first-class operation.** The deployment design locked
"bring up, measure, `terraform destroy`" because the EKS control plane
and NAT gateway bill by the hour. So nothing blocks a destroy:

```text
RDS            skip_final_snapshot = true, deletion_protection = false
S3             force_destroy = true
ECR            force_delete = true
FIRMS secret   recovery_window_in_days = 0
```

The consequence is stated plainly: **a destroy deletes every persisted
result, artifact and image**, and the FIRMS key must be written again
after each fresh apply. That matches the environment's purpose
(benchmarks and demos, with all results reproducible from the pipeline).
It is not a production-data posture.

## Validation actually run

Terraform is not installed natively on this machine (already noted in
the deployment design's tooling check). Every check below ran in the
official `hashicorp/terraform:1.16.4`
container instead, against the real providers and modules downloaded
from the registry:

```text
terraform fmt -check -recursive                 -> exit 0
terraform init -backend=false                   -> providers + 3 modules installed
terraform validate                              -> Success! The configuration is valid.
terraform providers lock -platform=windows_amd64 -platform=linux_amd64 -platform=darwin_arm64
                                                -> lock file usable natively on Windows
```

A static security scan also ran (`aquasec/trivy config`, HIGH/CRITICAL,
downloaded third-party modules excluded):

```text
first run    3 findings -- AWS-0031 x2 (mutable ECR tags), AWS-0132 (S3 without CMK)
fixed        AWS-0031: image_tag_mutability = "IMMUTABLE" (see above)
accepted     AWS-0132: SSE-S3, as already locked. A customer-managed KMS
             key would add a monthly key cost plus per-request KMS charges,
             and kms:Decrypt/GenerateDataKey on the backend role, for no
             requirement this project has (no key-policy or cross-account
             need). Bucket is private (all four Block Public Access flags)
             and owner-enforced.
final run    1 finding in this repository's code (the accepted AWS-0132)
```

What `validate` cannot check without an AWS account (credentials,
quotas, instance-type availability in `us-west-2`'s chosen AZs, the RDS
engine minor resolved from `"16"`) is exactly what a reviewed
`terraform plan` against a real account is for.

## Before the first real `terraform init`

Two one-time steps outside Terraform, both documented here so the
first real run follows them rather than improvising:

```bash
# 1. Install the AWS CLI and Terraform (or keep using the container), then
#    configure credentials for the target account.

# 2. Create the state bucket by hand -- it cannot live in the state it stores.
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
aws s3api create-bucket --bucket ai-earth-tfstate-$ACCOUNT_ID --region us-west-2 \
  --create-bucket-configuration LocationConstraint=us-west-2
aws s3api put-bucket-versioning --bucket ai-earth-tfstate-$ACCOUNT_ID \
  --versioning-configuration Status=Enabled
aws s3api put-public-access-block --bucket ai-earth-tfstate-$ACCOUNT_ID \
  --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
cp backend.hcl.example backend.hcl   # then set bucket = "ai-earth-tfstate-<account-id>"
terraform init -backend-config=backend.hcl
```

New S3 buckets are encrypted with SSE-S3 by default, and the backend
block sets `encrypt = true`. The state bucket is deliberately **not**
destroyed by `terraform destroy`, which is why it is created by hand.

After the first apply, the FIRMS key's value is written out of band, so
it never enters Terraform variables or state:

```bash
aws secretsmanager put-secret-value --secret-id ai-earth/firms \
  --secret-string '{"map_key":"<real FIRMS map key>"}'
```

## Outputs -> the cloud manifests

`environments/production/outputs.tf` exposes every value the cloud
manifests need, so none is hardcoded a second time
(`docs/cloud-deployment.md`, gaps 4-7):

```text
spring_datasource_url, postgres_user   -> ConfigMap
redis_host                             -> ConfigMap REDIS_HOST, KEDA trigger address
object_store_bucket                    -> ConfigMap OBJECT_STORE_BUCKET
db_master_user_secret_arn,
firms_secret_arn                       -> ExternalSecret remote refs
ecr_repository_urls                    -> Deployment images
backend_service_account                -> ServiceAccount the backend must run as
                                          (default/backend -- the Pod Identity
                                          association already points at it)
kubeconfig_command                     -> local kubectl access
```

## What this layout does not contain

- No Kubernetes application objects: the cloud copies of the backend and
  frontend Deployments, the `backend` ServiceAccount, the Ingress, the
  `ClusterSecretStore`/`ExternalSecret`, and the TLS-enabled KEDA
  `ScaledObject` are the cloud manifests'. That keeps application rollouts
  (`kubectl apply`) separate from infrastructure changes (`terraform apply`).
- No `plan`/`apply` output. That comes later, after reviewing the plan.
