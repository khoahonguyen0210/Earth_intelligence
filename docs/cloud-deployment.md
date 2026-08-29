# Cloud Deployment — LOCKED

This document freezes the AWS deployment per Task 12.1 of the Execution
Handbook, the first task of Phase 12. It is not a brainstorming
document. Task 12.2 lays out Terraform for exactly this, Task 12.3
provisions it, Task 12.4 deploys onto it; none of them reopen the
choices below.

Every version, add-on name and support claim below was checked against
the current AWS / Terraform / KEDA / Spring documentation while writing
this, not recalled -- see "Verified against" at the end.

## One region, one environment

```text
region:       us-west-2 (Oregon)
environment:  production (the only one -- Task 12.2's own
              infra/terraform/environments/production/ layout)
```

`us-west-2`, not `us-west-1` (N. California): the study region is
California, but no request path depends on latency to California. Both
subprocess scripts the backend invokes read local files baked into the
image -- `run_forecast_cli.py` and `run_analysis_cli.py` both read
`data/raw/firms/firms_sample.csv` (`backend/Dockerfile` copies
`data/raw`), and the live FIRMS fetch (`data.firms.fetch_firms_sample`)
is only called from offline scripts (`data/benchmark.py`,
`models/harness.py`), never per request. `us-west-2` is the cheaper
West Coast region, with more availability zones and every service below
at general availability.

## The six handbook items, mapped to one AWS service each

```text
AWS networking                 VPC, 2 AZs, public + private subnets,
                               1 NAT gateway, S3 gateway endpoint,
                               Application Load Balancer
managed relational database    Amazon RDS for PostgreSQL 16 (+ PostGIS)
S3                             Amazon S3, one private bucket
Kubernetes/container execution Amazon EKS 1.36 (managed node group) + ECR
Secrets Manager                AWS Secrets Manager -> External Secrets
                               Operator -> the existing ai-earth-secret
logging/metrics integration    CloudWatch (Container Insights + Logs)
```

Plus one item the handbook's list leaves out but the locked stack does
not: Redis. It becomes **Amazon ElastiCache (Redis OSS 7.1)**, not the
`infra/k8s/redis.yaml` pod -- the handbook's "do not build custom
equivalents of managed services" applies to it exactly as it does to
Postgres. Same reasoning retires `infra/k8s/postgres.yaml` (-> RDS) and
`infra/k8s/minio.yaml` (-> S3) in the cloud; all three stay as-is for
the local kind cluster.

## Networking

```text
VPC                10.0.0.0/16
public subnets     2 (one per AZ)   -- ALB, NAT gateway
private subnets    2 (one per AZ)   -- EKS nodes, RDS, ElastiCache
NAT gateway        1 (single AZ)
VPC endpoint       S3 gateway endpoint (free) on the private route tables
```

Nothing but the ALB and the NAT gateway gets a public IP. RDS and
ElastiCache accept connections only from the EKS node security group,
on 5432 and 6379 respectively.

The NAT gateway is required even though the request path makes no
outbound internet call (see above): nodes in private subnets must pull
third-party images from public registries -- KEDA and External Secrets
Operator from `ghcr.io`, among others -- and reach the EKS, ECR, STS,
Secrets Manager and CloudWatch APIs. Mirroring every third-party image
into ECR and adding an interface endpoint per AWS API would cost more
than the NAT gateway it replaces. The S3 gateway endpoint is free and
keeps artifact reads/writes (the backend's only high-volume AWS
traffic) off the NAT gateway's per-GB charge.

One NAT gateway, not one per AZ: losing that AZ's NAT stops image pulls
and AWS API calls from the other AZ until it is back, an accepted trade
for halving the fixed NAT cost on a single-environment project.

## Kubernetes: EKS 1.36, managed node group

```text
EKS version        1.36 (standard support until 2027-08-02)
node group         managed, m6i.large (2 vCPU / 8 GiB), min 2, max 4,
                   spread across both private subnets
container registry Amazon ECR: ai-earth-backend, ai-earth-frontend
```

1.36, the newest EKS release: 1.33 and older are already in EKS
extended support, which bills $0.60/cluster-hour instead of $0.10 --
6x the control-plane cost for no benefit on a new cluster.

EKS, not ECS: Phase 11 already locked real Kubernetes manifests and a
KEDA `ScaledObject` (`infra/k8s/autoscaling.yaml`); ECS would throw
both away. Managed node group, not Fargate: Fargate runs no DaemonSets,
which rules out the CloudWatch agent/Fluent Bit below, and Task 11.5
already measured backend boot as the dominant recovery cost (34.81 s)
-- Fargate's per-pod VM provisioning would add to it.

`m6i.large`, not burstable `t3`: Task 11.5 measured one backend pod at
~1.2 cores sustained while processing forecasts and ~3.5 cores while
booting. That is sustained load, which exhausts `t3` CPU credits. Two
nodes is the floor for AZ spread, not a capacity estimate; Task 12.5
measures real capacity.

Cluster components, all installed by Terraform, none hand-built:

```text
component                        installed as
vpc-cni, kube-proxy, coredns     EKS add-on (AWS)
eks-pod-identity-agent           EKS add-on (AWS)
amazon-cloudwatch-observability  EKS add-on (AWS), >= v3.1.0 for Pod Identity
metrics-server                   EKS add-on (community)
aws-load-balancer-controller     Helm, >= v2.7.0 for Pod Identity
keda                             Helm (the existing Redis-queue ScaledObject)
external-secrets                 Helm
reloader (stakater)              Helm (see "DB password rotation" below)
```

Pod IAM uses **EKS Pod Identity**, not static access keys and not IRSA.
It is AWS's recommended mechanism, needs no per-cluster OIDC provider,
and every component that calls AWS supports it at the versions above:

```text
service account              IAM permissions
backend                      S3 on the one artifact bucket (see S3)
external-secrets             secretsmanager:GetSecretValue/DescribeSecret
                             on the project's secrets only
aws-load-balancer-controller the controller's published IAM policy
cloudwatch-agent             CloudWatchAgentServerPolicy
```

External Secrets Operator has one Pod Identity constraint: its
`ClusterSecretStore` must omit the `auth` block (no `serviceAccountRef`),
because ESO cannot impersonate a service account whose role comes from
Pod Identity -- it authenticates as its own controller pod instead.

## Database: RDS for PostgreSQL 16

```text
engine           postgres 16 (latest 16.x minor at provisioning;
                 16.15 ships PostGIS 3.4.6)
instance         db.t4g.micro, single-AZ, private subnets only
storage          gp3, 20 GiB, encrypted, autoscaling to 50 GiB
extension        postgis (V1__initial_schema.sql already runs
                 CREATE EXTENSION IF NOT EXISTS postgis)
master password  RDS-managed (manage_master_user_password), stored in
                 Secrets Manager, never in Terraform variables or state
backups          7-day automated retention
```

RDS for PostgreSQL 16 ships PostGIS, and the master user has the
`rds_superuser` role that `CREATE EXTENSION postgis` needs -- so Flyway's
existing V1 migration runs unchanged; no separate extension-install step.
Not Aurora: nothing here needs Aurora's storage layer, and its minimum
cost is well above a `db.t4g.micro`. Single-AZ, not Multi-AZ: the same
single-environment cost trade as the NAT gateway. Instance size is a
starting point for Task 12.5 to measure, not a capacity claim.

## Redis: ElastiCache (Redis OSS)

```text
engine       Redis OSS 7.1, one cache.t4g.micro node, no replica
encryption   in transit (TLS) and at rest
```

Redis OSS, not Valkey: the stack locks Redis, and ElastiCache still
supports Redis OSS 7.1 with no announced end of standard support (only
v4-v6 have dates).

Single node, with a real, accepted risk: the queue is one Redis list,
while job state lives in Postgres (`Forecast` rows, Task 6.5). If the
node is lost, every id still sitting in the list is gone, and those
jobs stay `PENDING` in Postgres forever -- nothing re-enqueues them.
Task 6.6's retry covers a failed or timed-out Python subprocess, not a
lost queue entry. A replica shrinks this window but does not close it
(replication is asynchronous), and doubles the Redis cost; the actual
fix is a startup sweep that re-enqueues stale `PENDING` rows, which is
application reliability work for Phase 13, not infrastructure.

## Object storage: S3

```text
bucket           ai-earth-artifacts-<account-id> (bucket names are global;
                 injected via the existing OBJECT_STORE_BUCKET)
access           Block Public Access on, SSE-S3 encryption, versioning off
IAM              backend pod role: s3:GetObject/PutObject/DeleteObject on
                 the bucket's objects, s3:ListBucket on the bucket
```

Terraform creates the bucket. `S3ObjectStore`'s startup `headBucket`
(which S3 authorizes as `s3:ListBucket`) therefore succeeds and never
reaches its `createBucket` fallback in the cloud, which is why the pod
role gets no `s3:CreateBucket`.

## Secrets: Secrets Manager -> External Secrets Operator

```text
Secrets Manager secret             -> ai-earth-secret key
rds!db-... (RDS-managed) password  -> POSTGRES_PASSWORD
ai-earth/firms           map_key   -> FIRMS_MAP_KEY
```

External Secrets Operator, not the Secrets Store CSI driver (which is
also an EKS add-on now): an `ExternalSecret` writes an ordinary
Kubernetes Secret named `ai-earth-secret` with the same keys
`infra/k8s/backend.yaml` already reads through `secretKeyRef`. Task
11.1's ConfigMap/Secret split carries over unchanged, with no volume
mounts and no second secret-reading path in the backend. The CSI
driver's model is files mounted into the pod, which the backend would
need new code to read.

`FIRMS_MAP_KEY` is still required in the cloud, not just locally:
`load_firms_observations` (`query/run_analysis.py`) calls
`load_firms_config()` on every analysis, and that raises if the key is
unset, even though the analysis path only uses it for the product
name. It is written to Secrets Manager out of band (CLI or console),
never into Terraform variables or state.

`MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD` have no cloud counterpart: S3
access comes from the pod role above, not a key pair.

### DB password rotation

RDS rotates its managed master password **every 7 days by default**.
The backend reads `SPRING_DATASOURCE_PASSWORD` from its environment
once, at JVM start. So one week after `terraform apply`, every new
Hikari connection would fail authentication while old connections kept
working. That is a slow, confusing outage, not a crash.

Locked handling, using established tools rather than new code:

```text
ExternalSecret refreshInterval   5m   -- picks up the rotated password
reloader annotation on backend        -- rolling-restarts the Deployment
  (secret.reloader.stakater.com/          whenever ai-earth-secret changes
   reload: ai-earth-secret)
```

The worst-case window is one refresh interval plus one rolling restart.
It stays short because the rollout keeps the old pods, with their
still-valid open connections, until the new pods pass readiness.

## Ingress: one ALB, one origin

```text
ALB (internet-facing, HTTP :80), path routing:
  /analyses*  /forecasts*  /results*  /actuator/health  -> backend:8080
  /*                                                    -> frontend:80
```

The routed prefixes are exactly the backend's real controller mappings
(`POST /analyses`, `POST /forecasts`, `GET /analyses/{id}`,
`GET /results/{id}`, `GET /forecasts/{id}`, `GET /forecasts/{id}/result`)
plus the health endpoint.

The frontend stays on EKS behind the same ALB, rather than moving to
S3 + CloudFront. That gives the browser a single origin, so the
frontend calls the API by relative path and CORS never applies. A
separate static-hosting origin would need a cross-origin API URL,
CORS rules, and a second deployment path for no functional gain.

HTTP only, on the ALB's own AWS-assigned DNS name, for Phase 12: HTTPS
needs a domain name and an ACM certificate, which belong to Task 13.4's
security baseline, not to "stand the product up in AWS."

## Logging and metrics: CloudWatch

```text
container logs      Fluent Bit (amazon-cloudwatch-observability add-on)
                    -> CloudWatch Logs, 30-day retention
cluster/pod metrics Container Insights (same add-on)
RDS, ElastiCache,   native CloudWatch metrics, no extra agent
ALB, NAT
```

This is the handbook's "integration" -- plumbing AWS's own
logs/metrics sink into the cluster. The application-level structured
logging, Prometheus-compatible metrics and OpenTelemetry tracing locked
in the stack are Phase 13's (Tasks 13.1-13.3), and they ship through
this same agent rather than a second pipeline (the add-on already
supports OTLP ingestion from v6.2.0).

## Terraform state

```text
backend   S3 (separate state bucket, versioned, encrypted)
locking   S3-native lockfile (use_lockfile = true)
```

S3-native locking is the current mechanism. DynamoDB-based locking is
deprecated in the S3 backend, so no lock table is needed. The state
bucket is the one resource created by hand before `terraform init`;
Task 12.2 documents that bootstrap.

## Gaps the code must close before Task 12.4 can deploy

These are real couplings in the code as it stands today. Each one works
locally only because MinIO, the kind cluster, or the compose stack
happens to match a hardcoded value:

```text
1. S3ClientConfig             always sets endpointOverride, path-style access,
                              Region.US_EAST_1 and StaticCredentialsProvider.
                              Real S3 in us-west-2 needs: no endpoint override,
                              the real region, and DefaultCredentialsProvider
                              (which picks up Pod Identity) when no static
                              key is configured.
2. frontend/src/api/client.ts API_BASE_URL is hardcoded
                              "http://localhost:8080". Behind the one-origin
                              ALB it must be a relative base, set at build time.
3. Redis TLS                  ElastiCache in-transit encryption needs
                              SPRING_DATA_REDIS_SSL_ENABLED=true (property
                              spring.data.redis.ssl.enabled, unchanged in the
                              backend's Spring Boot 4.1.1) and the KEDA redis
                              trigger's enableTLS: "true" (trigger metadata).
4. KEDA trigger address       autoscaling.yaml hardcodes
                              redis.default.svc.cluster.local:6379; the cloud
                              value is the ElastiCache primary endpoint.
5. ConfigMap                  SPRING_DATASOURCE_URL, REDIS_HOST,
                              OBJECT_STORE_BUCKET point at in-cluster
                              services; the cloud values come from Terraform
                              outputs (RDS endpoint, ElastiCache endpoint,
                              bucket name).
6. Images                     backend.yaml/frontend.yaml reference
                              ai-earth-*:local with imagePullPolicy
                              IfNotPresent; the cloud references ECR image URIs.
7. Secret rotation            backend.yaml has no reloader annotation, and no
                              ExternalSecret exists yet (see "DB password
                              rotation").
8. Trace export               the backend exports spans only when
                              OTEL_EXPORTER_OTLP_TRACES_ENDPOINT is set
                              (Task 13.3, docs/tracing.md). No manifest sets
                              it (kind has no collector); the cloud ConfigMap
                              points it at the CloudWatch agent's OTLP
                              receiver, verified against the add-on in 12.4.
```

Items 1-3 are code or config changes and belong to Task 12.4. Items 4-8
are per-environment manifest values, so the cloud copies of these
manifests will take them from Terraform outputs instead of hardcoding
them a second time.

KEDA's `maxReplicaCount: 2` is **not** carried over as a cloud decision.
Task 11.4 derived it from a single-machine kind cluster where replicas
share one CPU pool. On EKS, replicas land on separate nodes, so the
ceiling is re-measured in Task 12.5 instead of copied.

## Local tooling Task 12.2/12.3 need, checked on this machine

```text
kubectl    present (Docker Desktop's bundled binary)
docker     present
terraform  MISSING -- needed from Task 12.2 (terraform fmt/validate)
aws CLI    MISSING -- needed from Task 12.3 (credentials, state bucket
           bootstrap, aws eks update-kubeconfig)
helm       not required locally -- Terraform's helm provider installs
           the charts above
```

## Approximate fixed cost while running

On-demand list prices, rounded, before any traffic or data transfer.
These are estimates, not measurements (Task 12.5 records the real
cost):

```text
EKS control plane (standard support)  $0.10/h   ~$73 / month
2 x m6i.large                         $0.096/h  ~$140 / month
NAT gateway (1)                       $0.045/h  ~$33 / month + data processed
ALB                                   $0.0225/h ~$16 / month + LCUs
RDS db.t4g.micro + 20 GiB gp3         $0.016/h  ~$15 / month
ElastiCache cache.t4g.micro           $0.016/h  ~$12 / month
total                                           ~$290 / month
```

The EKS control plane and the NAT gateway bill by the hour whether or
not anything is running. The environment is therefore meant to be
brought up for Tasks 12.3-12.5 and later demos, then taken down with
`terraform destroy`, not left running.

## What this document does not define

- The Terraform module layout is Task 12.2's.
- Running `init`/`plan`/`apply` is Task 12.3's.
- Closing the seven gaps above and verifying health, Earth analysis,
  forecast, async jobs and persistent results on AWS is Task 12.4's.
- Task 13.4's security baseline covers HTTPS, a domain, and the rest of
  the hardening, including `management.endpoint.health.show-details=always`,
  which would expose component details on the public ALB.
- Re-enqueuing stranded `PENDING` jobs is Phase 13 reliability work.

## Verified against

```text
EKS versions / support dates   docs.aws.amazon.com/eks/latest/userguide/kubernetes-versions.html
EKS pricing                    aws.amazon.com/eks/pricing
EKS add-ons (AWS, community)   docs.aws.amazon.com/eks/latest/userguide/workloads-add-ons-available-eks.html,
                               .../community-addons.html
CloudWatch add-on + Pod Id.    docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/install-CloudWatch-Observability-EKS-addon.html
RDS PG16 PostGIS versions      docs.aws.amazon.com/AmazonRDS/latest/PostgreSQLReleaseNotes/postgresql-extensions.html
RDS managed password rotation  docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-secrets-manager.html
ElastiCache engine versions    docs.aws.amazon.com/AmazonElastiCache/latest/dg/engine-versions.html
Terraform S3 backend locking   developer.hashicorp.com/terraform/language/backend/s3
KEDA redis-lists enableTLS     keda.sh/docs/latest/scalers/redis-lists
Spring Boot 4.0 prop. changes  github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Configuration-Changelog
ESO / LB controller Pod Id.    external-secrets.io/latest/provider/aws-access,
                               github.com/kubernetes-sigs/aws-load-balancer-controller/issues/3503
```
