# Kubernetes Manifests

This document describes the Kubernetes manifests. They were written and
checked against the Kubernetes schema here. Deploying them to a local
cluster is covered in `docs/local-kubernetes-deployment.md`.

## Prerequisites

```text
[x] local distributed execution works    docs/one-worker-baseline.md,
                                         docs/multi-worker-scaling.md
[x] worker model is stable               WorkflowExecutor,
                                         run_distributed_inference
[x] Docker images work                   docs/docker-images.md,
                                         docs/clean-start-test.md
[x] distributed benchmark exists         docs/multi-worker-scaling.md
```

## Manifests

```text
infra/k8s/configmap.yaml       non-secret app config
infra/k8s/secret.example.yaml  secret template (the real secret.yaml is
                               ignored by git, like .env and .env.example)
infra/k8s/postgres.yaml        Deployment + Service + PVC
infra/k8s/redis.yaml           Deployment + Service + PVC
infra/k8s/minio.yaml           Deployment + Service + PVC
infra/k8s/backend.yaml         Deployment + Service (NodePort 30080)
infra/k8s/frontend.yaml        Deployment + Service (NodePort 30173)
```

The plan named four deployables: backend, worker, frontend and redis.
There is no separate `worker` manifest, for the reason given in
`docs/docker-images.md`. The Java-to-Python bridge
(`PythonForecastRunner`, `PythonAnalysisRunner`) starts a subprocess on
the same machine with `ProcessBuilder`; it is not a network call. So
there is no separate worker process that could have its own
Deployment. `backend.yaml` fills both roles, as `backend/Dockerfile`
does. It follows that worker replica scaling changes
`spec.replicas` of `backend`, not a separate resource.

Postgres and MinIO were not in the list of four either, but the backend
cannot start without them (Flyway migrations, JPA `ddl-auto: validate`
and the object-store client). Without them, `backend` would crash and
restart in a loop on any cluster. The five-service Compose stack in
`docs/docker-compose-stack.md` made the same choice.

## ConfigMap and Secret

Not secret (`configmap.yaml`): `POSTGRES_DB`, `POSTGRES_USER`,
`SPRING_DATASOURCE_URL`, `REDIS_HOST`, `OBJECT_STORE_ENDPOINT`,
`OBJECT_STORE_BUCKET`.

Secret (`secret.example.yaml` is a template only; the values go in
`infra/k8s/secret.yaml`, which git ignores): `POSTGRES_PASSWORD`,
`MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`, `FIRMS_MAP_KEY` (the NASA
FIRMS key that, as `docs/clean-start-test.md` found, the container
always needs).

`GEMINI_API_KEY` and `CDSAPI_KEY` (also in `.env.example`) are in
neither manifest. The backend's `ProcessBuilder` bridge calls only two
scripts, `scripts/query/run_analysis_cli.py` and
`scripts/query/run_forecast_cli.py`, and a `grep` over both confirms
that neither reads these keys. They belong to the standalone planner
command and the ERA5 download scripts, which do not run when a backend
pod handles a request.

## Database credentials

`application.properties` sets `spring.datasource.username` and
`spring.datasource.password` to fixed defaults (`ai_earth` and
`ai_earth_dev`), not to `${ENV_VAR:default}` placeholders like the
other settings. The Compose stack never showed the problem, because its
`postgres` service uses the same fixed credentials, and
`docker-compose.yml` only overrides `SPRING_DATASOURCE_URL`. In
Kubernetes, once `secret.yaml` sets a different `POSTGRES_PASSWORD`,
the backend would still connect with `ai_earth_dev` and fail to log in.

The fix also sets `SPRING_DATASOURCE_USERNAME` and
`SPRING_DATASOURCE_PASSWORD` (the same Spring relaxed binding that
`SPRING_DATASOURCE_URL` uses) from the same `ConfigMap` and `Secret`
keys that the `postgres.yaml` container reads. Both pods then always
agree, whatever `secret.yaml` contains. For the same reason,
`OBJECT_STORE_ACCESS_KEY` and `OBJECT_STORE_SECRET_KEY` in
`backend.yaml` read `MINIO_ROOT_USER` and `MINIO_ROOT_PASSWORD`
directly, instead of copying the values into a second key that could
fall out of step.

## The frontend's `localhost:8080`

`frontend/Dockerfile` builds `http://localhost:8080` into the bundle;
the browser calls that address directly, as in the Compose stack. A
NodePort is a different address. The `backend.yaml` Service publishes
`30080`, not `8080`, because by default the Kubernetes API server only
accepts NodePort values from `30000-32767`. Port `30080` is still useful
for calling the API or health checks from the host, but a browser using
the frontend needs the backend at `localhost:8080`. The deployment step
provides this with `kubectl port-forward svc/backend 8080:8080`, or an
Ingress or LoadBalancer could map port 8080. The manifests alone cannot
solve this without breaking the API server's port range.

## Validation

No local cluster existed when the manifests were written
(`kubectl cluster-info` could not connect), so they were checked
against the Kubernetes API schema instead of with `kubectl apply`:

```text
kubeconform -strict -kubernetes-version 1.31.0 -summary infra/k8s/*.yaml
Summary: 15 resources found in 7 files - Valid: 15, Invalid: 0, Errors: 0, Skipped: 0
```

`-strict` also rejects unknown fields, so this is a structural check
against the v1.31 OpenAPI schema, not only a check that the YAML
parses. The local `kubectl` was the v1.36 client with no server to
validate against.

## Out of scope

Choosing and installing a local cluster, applying the manifests, and
checking API health, worker health, job execution, service connections
and restart behavior are covered in
`docs/local-kubernetes-deployment.md`.
