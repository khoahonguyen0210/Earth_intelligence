# Autoscaling

The `backend` Deployment, which serves the API and also runs the worker
(see `docs/kubernetes-manifests.md`), scales on the length of the Redis
forecast queue. The settings below come from measurements on the same
kind cluster, and scaling was checked on that cluster.

## Why KEDA

A plain Kubernetes `HorizontalPodAutoscaler` scales only on CPU and
memory by default. Scaling on another signal, such as the length of a
Redis list, usually needs a custom metrics pipeline (Prometheus and
prometheus-adapter). KEDA (v2.17.1, `keda` namespace, installed from
its single official manifest without Helm) has a built-in `redis`
scaler. It reads `LLEN` on a Redis key and drives a standard HPA that
it creates and manages. This avoids the extra pipeline for one signal.

```bash
kubectl apply --server-side -f https://github.com/kedacore/keda/releases/download/v2.17.1/keda-2.17.1.yaml
```

## The ScaledObject: `infra/k8s/autoscaling.yaml`

```text
trigger:            redis, address redis.default.svc.cluster.local:6379,
                    listName "forecast-jobs" (the queue key in
                    RedisForecastQueue.java)
listLength:         1    scale up when even one job is waiting
minReplicaCount:    1
maxReplicaCount:    2
pollingInterval:    10s
cooldownPeriod:     60s  KEDA's delay before scaling down
scaleDown.stabilizationWindowSeconds: 60   the HPA's window against
                                           rapid up and down changes
```

**`minReplicaCount` is 1, not 0.** A pure worker could scale to zero
when the queue is empty. But `backend` also serves the HTTP API, and
there is no separate worker Deployment
(`docs/kubernetes-manifests.md`). Scaling to zero would take the whole
API down whenever the queue is empty, which is most of the time.

**`maxReplicaCount` is 2, because measurements on this cluster show
that more replicas make it slower.** `docs/worker-replica-scaling.md`
ran the fixed workload at 1, 2, 4 and 8 replicas on the same kind
cluster. Throughput peaked at 2 replicas (0.156 jobs/s) and fell below
the 1-replica baseline by 8 replicas (0.071 jobs/s). Kind runs the
whole cluster as one container on one machine, so replicas share the
same CPU and memory instead of getting their own hardware. A higher
limit would let the autoscaler move into a range that is known to
perform worse.

## Bug found: short Service name looked up in the wrong namespace

At first, every poll failed with `connection to redis failed: dial tcp:
lookup redis: i/o timeout`. The KEDA operator that evaluates the
trigger runs in the `keda` namespace, not `default`. Kubernetes looks
up a short Service name in the caller's namespace first, so `redis`
from a pod in `keda` became `redis.keda.svc.cluster.local`, which does
not exist. The Service created in `docs/kubernetes-manifests.md` is
`redis.default.svc.cluster.local`. The fix uses the full name in the
trigger's `address`.

## Check: scaling under a queue backlog

Four forecast requests were sent one after another to a deployment
running 1 replica, and `kubectl get hpa,deployment` was polled every
8 s:

```text
t=8s          queue depth 3/1 (avg); backend already 1/2 (new pod starting)
t=16s         metric 1.5/1 (avg); HPA target reached 2 replicas
t=56s         metric 0/1 (avg), backend 2/2; queue empty, both replicas Ready
t=80s         backend back to 1/1; scaled down once
t=88s..144s   steady at 1/1; no oscillation
```

Scale-up began within one polling interval of the load. The count never
went above `maxReplicaCount: 2`. Scale-down happened once, after the
queue was empty, and the count stayed at `minReplicaCount` for the rest
of the window, without switching back and forth between 1 and 2.

## Out of scope

The full Kubernetes benchmark is covered in
`docs/kubernetes-benchmark.md`.
