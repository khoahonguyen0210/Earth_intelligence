# Local Kubernetes Deployment

This deployment checks the manifests in `docs/kubernetes-manifests.md`
by running them on a local cluster, not only by reading them. The
clean-start test (`docs/clean-start-test.md`) does the same for the
Docker stack.

## Cluster: kind

kind (Kubernetes in Docker, v0.27.0) was chosen over minikube. It runs
as one container on the Docker daemon that was already installed, and
needs no separate VM or hypervisor driver and no extra disk space
beyond one node image of about 1 GB. Before this, the machine had only
`kubectl` (client only, v1.36.1) and no running cluster. The config is
`infra/kind/kind-config.yaml`.

```bash
kind create cluster --name ai-earth --config infra/kind/kind-config.yaml
```

## Images: reused, not rebuilt

`ai-earth-backend:local` and `ai-earth-frontend:local` are the same
images that the clean-start test checked (`docker tag
docker-backend:latest ai-earth-backend:local`, and the same for the
frontend). Nothing in `backend/`, `frontend/` or `ml/` had changed, so a
rebuild would only produce the same image. Kind nodes run their own
containerd, separate from the host's Docker image store, so both images
were loaded into the cluster:

```bash
kind load docker-image ai-earth-backend:local --name ai-earth
kind load docker-image ai-earth-frontend:local --name ai-earth
```

## Two bugs found on the cluster

Schema validation could not catch either of these.

**1. Environment variables added by Kubernetes clashed with
`application.properties`.** Unless `enableServiceLinks: false` is set,
every pod gets a Docker-links-style variable for each Service in its
namespace, for example `REDIS_PORT=tcp://<cluster-ip>:6379` for a
Service named `redis`. The placeholder
`spring.data.redis.port=${REDIS_PORT:6379}` in `application.properties`
uses the same name, so the backend pod crashed on start with `Failed to
bind properties under 'spring.data.redis.port' to int ...
NumberFormatException: For input string: "tcp://10.96.32.85:6379"`.
Docker Compose adds no such variables, so the earlier Docker work could
not have caught this. The fix adds `enableServiceLinks: false` to the
pod spec in `backend.yaml`.

**2. The MinIO image could no longer be pulled.** `quay.io/minio/minio`
and `minio/minio` both return "unauthorized", because MinIO stopped
publishing community images. `minio.yaml` and the Compose file now use
`bitnamilegacy/minio`. It runs as user 1001, so the pod sets
`fsGroup: 1001` for the data volume.

## Checks on the cluster

```text
[x] API health           GET /actuator/health -> {"status":"UP",
                         db: UP, redis: UP}, through localhost:8080.
                         The extraPortMappings in kind-config.yaml send
                         host ports 8080 and 5173 to the backend and
                         frontend NodePorts 30080 and 30173, so no
                         kubectl port-forward is needed. This solves
                         the localhost:8080 issue noted in
                         docs/kubernetes-manifests.md in a different way
                         than that document expected.
[x] worker health        the worker runs in the backend pod (see
                         docs/kubernetes-manifests.md), so the same
                         health check covers it
[x] job execution        POST /analyses -> GET /results/{id}: the Earth
                         analysis succeeds with {"result":{"count":198}, ...}
                         for the same California 2024-08-01..20 query as
                         docs/clean-start-test.md; the same result with a
                         different orchestrator.
                         POST /forecasts -> GET /forecasts/{id}/result:
                         ends in FAILED with the same known
                         "single-class training split" error
                         (docs/clean-start-test.md), which shows that this
                         was a data limit, not a Docker problem
[x] service connections  Flyway migration, JPA validation, Redis ping and
                         MinIO-backed evidence storage all worked through
                         the cluster DNS (the postgres, redis and minio
                         Service names); no application code knows it is
                         not talking to localhost
[x] restart behavior     `kubectl delete pod` on the running backend pod:
                         the Deployment controller created a new pod by
                         itself, which reached 1/1 Ready in about 47 s
                         (JVM start, Flyway, JPA, Redis and MinIO
                         connections), and the Service sent
                         /actuator/health to the new pod with no manual
                         step
```

## Out of scope

Running the fixed workload at 1, 2, 4 and 8 backend replicas is in
`docs/worker-replica-scaling.md`. Autoscaling on Redis queue depth is in
`docs/autoscaling.md`. The benchmark is in
`docs/kubernetes-benchmark.md`.
