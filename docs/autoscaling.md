# Autoscaling — LOCKED

This document freezes Redis-queue-depth autoscaling. It is not a
brainstorming document. It scales
`backend` (the folded backend+worker role, `docs/kubernetes-
manifests.md`) on real queue depth, verified against the real kind
cluster already deployed and informed directly by measured data
already gathered, not a fresh guess at reasonable-sounding numbers.

## Why KEDA

A plain Kubernetes `HorizontalPodAutoscaler` only scales on CPU/memory
out of the box; scaling on an arbitrary signal like "Redis list length"
normally needs a custom-metrics pipeline (Prometheus + prometheus-
adapter). KEDA (v2.17.1, `keda` namespace, installed from the project's
single official manifest -- no Helm) has a built-in `redis` scaler that
polls `LLEN` on a real Redis key directly and drives a standard HPA it
creates and manages underneath, avoiding that whole extra pipeline for
one signal.

```bash
kubectl apply --server-side -f https://github.com/kedacore/keda/releases/download/v2.17.1/keda-2.17.1.yaml
```

## The ScaledObject: `infra/k8s/autoscaling.yaml`

```text
trigger:            redis, address redis.default.svc.cluster.local:6379,
                     listName "forecast-jobs" (RedisForecastQueue.java's
                     real queue key)
listLength:         1   -- scale-up threshold: any single job still
                           queued (not yet picked up) drives scale-up
minReplicaCount:    1
maxReplicaCount:    2
pollingInterval:    10s
cooldownPeriod:     60s -- KEDA's own scale-down delay
scaleDown.stabilizationWindowSeconds: 60 -- HPA's own anti-flap window
```

**`minReplicaCount` is 1, not 0.** A pure worker could reasonably scale
to zero on an empty queue, but `backend` also serves the HTTP API
(`docs/kubernetes-manifests.md` already established there is no separate
worker Deployment to scale independently) -- scaling to zero here would
take the whole API down every time the forecast queue is empty, which
is most of the time. This is a direct, structural consequence of the
architecture decision already locked earlier, not a new choice
made freely in this task.

**`maxReplicaCount` is 2, not higher, because measuring this
exact cluster found out that a higher ceiling would be wrong.**
`docs/worker-replica-scaling.md` ran the real fixed workload at 1/2/4/8
replicas on this same kind cluster and found throughput peaks at 2
replicas (0.156 jobs/s) then gets *worse* than the 1-replica baseline by
8 replicas (0.071 jobs/s) -- `kind` runs the whole cluster as one
container on one physical machine, so replicas here contend for one
fixed real CPU/RAM pool rather than getting independent hardware.
Setting `maxReplicaCount` any higher than 2 would let the autoscaler
"scale into" a regime this project already has direct, real evidence
performs worse, not better.

## A real bug this task found: bare Service name resolved in the wrong namespace

The first apply failed every poll: `connection to redis failed: dial
tcp: lookup redis: i/o timeout`. The KEDA operator that evaluates this
trigger runs in the `keda` namespace, not `default` -- Kubernetes'
default DNS search order resolves a bare Service name within the
*caller's own* namespace first, so `redis` from a `keda`-namespace pod
tried (and failed to find) `redis.keda.svc.cluster.local`, not the real
`redis.default.svc.cluster.local` `docs/kubernetes-manifests.md`
actually created. Fixed by using the fully-qualified name in the
trigger's `address`.

## Verification: a real queue backlog, watched scaling live

Four real forecast requests submitted back to back against a
steady-state 1-replica deployment, then `kubectl get hpa,deployment`
polled every 8s:

```text
t=8s    queue depth 3/1 (avg) -- backend already 1/2 (new pod starting)
t=16s   metric 1.5/1 (avg)    -- HPA target reached 2 replicas
t=56s   metric 0/1 (avg), backend 2/2 -- queue fully drained, both replicas Ready
t=80s   backend back to 1/1  -- scaled down cleanly, no flapping
t=88s..144s   steady at 1/1  -- confirmed stable, no oscillation
```

Scale-up reacted within one polling interval of real load appearing;
`maxReplicaCount: 2` was never exceeded; scale-down happened once,
cleanly, after the queue was confirmed empty, and stayed at
`minReplicaCount` for the remainder of the observation window -- no
flapping between 1 and 2.

## What this document does not define

Running the Kubernetes benchmark suite end to end is a separate job, still to come.
