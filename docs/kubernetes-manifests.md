# Kubernetes Manifests — LOCKED

This document freezes the Kubernetes manifests. It is not a
brainstorming document. Later work deploys these to a real local
cluster and verifies them; this task only writes and schema-validates
them.

## Entry condition, checked before starting

```text
[x] local distributed execution works    -- docs/one-worker-baseline.md,
    docs/multi-worker-scaling.md
[x] worker model is stable               -- WorkflowExecutor,
    run_distributed_inference
[x] Docker images work                   -- docs/docker-images.md,
    docs/clean-start-test.md
[x] distributed benchmark exists         -- docs/multi-worker-scaling.md
```

All four were already real and locked before this task started.

## Five manifests, not the literal four

```text
infra/k8s/configmap.yaml       -- non-secret app config
infra/k8s/secret.example.yaml  -- secret template (real secret.yaml is gitignored,
                                   same treatment as .env/.env.example)
infra/k8s/postgres.yaml        -- Deployment + Service + PVC
infra/k8s/redis.yaml           -- Deployment + Service + PVC
infra/k8s/minio.yaml           -- Deployment + Service + PVC
infra/k8s/backend.yaml         -- Deployment + Service (NodePort 30080)
infra/k8s/frontend.yaml        -- Deployment + Service (NodePort 30173)
```

The plan names four deployables: backend, worker, frontend, redis. There
is no separate `worker` manifest here, for the same real reason
`docs/docker-images.md` already found and already locked:
The Java-to-Python bridge (`PythonForecastRunner`/`PythonAnalysisRunner`)
is a same-machine `ProcessBuilder` subprocess call, not a network call --
there is no independently addressable worker process to give its own
Deployment. `backend.yaml` plays both roles, exactly as
`backend/Dockerfile` already does. This also means later "worker
replica scaling" work scales `backend`'s `spec.replicas`, not a separate
resource -- worth stating now since it changes what that work actually
measures.

Postgres and MinIO are not in the four-item list either, but
both are real, already-locked dependencies the backend
cannot start without (Flyway migrations, JPA `ddl-auto: validate`, the
object-store client) -- omitting them would make `backend` crash-loop on
every real cluster, not just a hypothetical one. This mirrors the same
call `docs/docker-compose-stack.md` already made for the five-service
compose stack.

## ConfigMap/Secret split

Non-secret (`configmap.yaml`): `POSTGRES_DB`, `POSTGRES_USER`,
`SPRING_DATASOURCE_URL`, `REDIS_HOST`, `OBJECT_STORE_ENDPOINT`,
`OBJECT_STORE_BUCKET`.

Secret (`secret.example.yaml`, template only -- real values go in a
gitignored `infra/k8s/secret.yaml`): `POSTGRES_PASSWORD`,
`MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`, `FIRMS_MAP_KEY` (the same real
NASA FIRMS credential `docs/clean-start-test.md` already found the
container needs unconditionally).

`GEMINI_API_KEY`/`CDSAPI_KEY` (also in `.env.example`) are not in either
manifest: `scripts/query/run_analysis_cli.py` and
`scripts/query/run_forecast_cli.py` -- the only two scripts the backend's
`ProcessBuilder` bridge actually invokes -- never reference them; they
belong to the standalone planner CLI and the ERA5 adapter's own
scripts, neither of which runs inside a backend pod's request path.
Checked directly (`grep` over both CLI scripts) rather than assumed.

## A real coupling `docker-compose.yml` never had to expose

`application.properties` hardcodes `spring.datasource.username`/
`spring.datasource.password` as literal defaults (`ai_earth`/
`ai_earth_dev`), not `${ENV_VAR:default}` placeholders like every other
setting in that file. The Docker Compose stack never noticed because its
`postgres` service also hardcodes the same literal credentials --
`docker-compose.yml` only ever needed to override `SPRING_DATASOURCE_URL`.
Kubernetes changes this the moment `secret.yaml` sets a real, non-default
`POSTGRES_PASSWORD`: `backend.yaml` would still connect with the
hardcoded `ai_earth_dev` default and fail authentication. Fixed by also
pointing `SPRING_DATASOURCE_USERNAME`/`SPRING_DATASOURCE_PASSWORD` (Spring's
same relaxed-binding mechanism `SPRING_DATASOURCE_URL` already relies on)
at the identical `ConfigMap`/`Secret` keys `postgres.yaml`'s own container
reads, so both pods always agree regardless of what `secret.yaml`
contains. The same reasoning is why `backend.yaml`'s
`OBJECT_STORE_ACCESS_KEY`/`OBJECT_STORE_SECRET_KEY` read `MINIO_ROOT_USER`/
`MINIO_ROOT_PASSWORD` directly rather than duplicating the same value
under a second secret key that could drift out of sync.

## The frontend's hardcoded `localhost:8080` on a real cluster

`frontend/Dockerfile` bakes `http://localhost:8080` into the built bundle
(the browser calls it directly, unchanged from the compose stack). A
NodePort is not the same address: `backend.yaml`'s Service publishes
`30080`, not `8080`, because the Kubernetes API server rejects NodePort
values outside `30000-32767` by default. `30080` remains useful for
direct API/health-check access from the host, but a browser hitting the
frontend still needs the backend reachable at exactly `localhost:8080` --
that is later deployment work's job -- `kubectl port-forward
svc/backend 8080:8080` (or an Ingress/LoadBalancer that maps to port
8080 directly) -- not something
these manifests can fix on their own without contradicting the API
server's own port-range constraint.

## Validation actually run, not just visual inspection

No local cluster exists yet on this machine (`kubectl cluster-info`
refuses to connect -- later deployment work chooses and installs one). So the real
check available at this stage is schema validation against the actual
Kubernetes API schema, not a live `kubectl apply`:

```text
kubeconform -strict -kubernetes-version 1.31.0 -summary infra/k8s/*.yaml
Summary: 15 resources found in 7 files - Valid: 15, Invalid: 0, Errors: 0, Skipped: 0
```

`-strict` also rejects unknown fields, so this is a real structural check
against the v1.31 OpenAPI schema (this machine's `kubectl` is v1.36
client-only, with no server to validate against yet), not merely "the
YAML parses."

## What this document does not define

Choosing and installing a local cluster, actually applying these
manifests, and verifying API health / worker health / job execution /
service connectivity / restart behavior is later deployment work's
job, not this document's.
