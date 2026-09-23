# Local Kubernetes Deployment — LOCKED

This document freezes the local Kubernetes deployment. It is not a
brainstorming document. It verifies
`docs/kubernetes-manifests.md` by actually deploying to a
real local cluster, the same "don't just look correct on paper" bar
`docs/clean-start-test.md` already set for the Docker stack.

## Cluster choice: kind

`kind` (Kubernetes-in-Docker, v0.27.0) over minikube: it runs as a single
container on the Docker daemon already installed and needs --
no separate VM/hypervisor driver, no extra disk footprint beyond one
~1GB node image. Only `kubectl` (client-only, v1.36.1) was present on
this machine beforehand; no cluster was running. Config:
`infra/kind/kind-config.yaml`.

```bash
kind create cluster --name ai-earth --config infra/kind/kind-config.yaml
```

## Images: reused, not rebuilt

`ai-earth-backend:local`/`ai-earth-frontend:local` are the exact images
the clean-start test already verified (`docker tag
docker-backend:latest ai-earth-backend:local`, same for frontend) --
nothing changed in `backend/`, `frontend/`, or `ml/` since then, so
rebuilding would only reproduce the same image. kind nodes run their own
containerd, separate from the host's Docker image store, so both were
pushed in explicitly:

```bash
kind load docker-image ai-earth-backend:local --name ai-earth
kind load docker-image ai-earth-frontend:local --name ai-earth
```

## Two real bugs a live cluster caught that schema validation could not

**1. Kubernetes' own auto-injected env vars collided with
`application.properties`.** Every pod gets a Docker-links-style env var
per Service already running in its namespace (`REDIS_PORT=tcp://<cluster
-ip>:6379` for a Service named `redis`) unless `enableServiceLinks:
false` is set. `application.properties`' `spring.data.redis.port=
${REDIS_PORT:6379}` placeholder happens to share that exact generic
name -- the backend pod crash-looped on boot with `Failed to bind
properties under 'spring.data.redis.port' to int ... NumberFormatException:
For input string: "tcp://10.96.32.85:6379"`. This is a real Kubernetes
platform behavior with no Docker Compose equivalent (compose has no
auto env-injection), so nothing in the earlier Docker work could have caught it. Fixed
by adding `enableServiceLinks: false` to `backend.yaml`'s pod spec.

**2. The MinIO image was no longer pullable.** `quay.io/minio/minio` and
`minio/minio` both return unauthorized, since MinIO stopped publishing
community images. `minio.yaml` and the Compose file now use
`bitnamilegacy/minio`, which runs as user 1001, so the pod sets
`fsGroup: 1001` for the data volume.

## Verification, run against the real cluster

```text
[x] API health          -- GET /actuator/health -> {"status":"UP",
    db: UP, redis: UP}, through localhost:8080 (kind-config.yaml's
    extraPortMappings route host 8080/5173 straight to backend/
    frontend's NodePorts 30080/30173 -- no kubectl port-forward needed,
    resolving docs/kubernetes-manifests.md's noted localhost:8080
    constraint a different way than that document anticipated)
[x] worker health       -- same process/pod as backend (the folded
    role docs/kubernetes-manifests.md already established); covered by
    the same health check
[x] job execution       -- POST /analyses -> GET /results/{id}: a real
    Earth analysis succeeds, {"result":{"count":198}, ...} for the
    same California/2024-08-01..20 query docs/clean-start-test.md used
    -- identical real result, different orchestrator.
    POST /forecasts -> GET /forecasts/{id}/result: reaches FAILED with
    the same real, already-documented "single-class training split"
    error (docs/clean-start-test.md) -- confirms this is a real,
    environment-independent data limitation, not a Docker-specific one
[x] service connectivity -- backend's Flyway migration, JPA validate,
    Redis ping, and MinIO-backed evidence storage all succeeded through
    Kubernetes' in-cluster DNS (postgres/redis/minio Service names),
    with zero application code aware it is not talking to localhost
[x] restart behavior     -- `kubectl delete pod` on the running backend
    pod; the Deployment controller recreated it unprompted, it reached
    1/1 Ready in ~47s (JVM boot + Flyway + JPA + Redis/MinIO
    reconnection), and the Service routed /actuator/health to the new
    pod with no manual re-registration
```

## What this document does not define

Running the fixed workload at 1/2/4/8 backend replicas is later
replica-scaling work's job. Configuring autoscaling on Redis queue
depth is later autoscaling-configuration work's job. Benchmarking the
result is later benchmarking work's job.
