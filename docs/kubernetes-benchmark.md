# Kubernetes Benchmark — LOCKED

This document freezes the Kubernetes benchmark. It is not a
brainstorming document. It records the six metrics the handbook asks
for -- runtime, throughput, speedup, efficiency, resource usage, failure
recovery -- against the real kind cluster earlier Kubernetes work built,
reusing already-locked real measurements where they exist rather than
re-deriving them.

## Runtime, throughput, speedup, efficiency

Not re-measured here: `docs/worker-replica-scaling.md`
already ran the real fixed 8-job workload at 1/2/4/8 replicas on this
exact cluster. Re-running the same sweep again would only reproduce it
with ordinary run-to-run noise, the same reason later distributed-scaling
work didn't redo the multi-worker scaling benchmark's own scaling sweep.
Speedup/efficiency are computed fresh from
those real numbers (`compute_speedup_efficiency`,
`ml/.../kubernetes/replica_scaling.py`, the handbook's own
`speedup(n)=T1/Tn`, `efficiency(n)=speedup(n)/n` formulas, matching
the multi-worker scaling benchmark's `distributed/scaling.py`):

```text
replicas   runtime_s   throughput_jobs_per_s   speedup   efficiency
1           64.29      0.124                   1.000     1.000
2           51.33      0.156                   1.252     0.626
4           56.76      0.141                   1.133      0.283
8          111.94      0.071                   0.574     0.072
```

Same conclusion as the worker replica scaling benchmark, now expressed in the handbook's own
speedup/efficiency terms: efficiency collapses monotonically past 2
replicas, and 8 replicas is slower (speedup < 1) than running just one.

## Resource usage

Real `kubectl top pods` samples (metrics-server installed for this task
-- kind ships none by default -- patched with `--kubelet-insecure-tls`,
the standard fix for kind's self-signed kubelet certs), idle versus
under a genuine KEDA-driven scale-up (8 real forecast requests
submitted, not a synthetic bypass of the autoscaler):

```text
idle, 1 replica:
  backend-...-44zh6    14m CPU     656 MiB

under load, mid scale-up to 2 replicas:
  backend-...-44zh6  1248m CPU     790 MiB   (already-running pod, now processing jobs)
  backend-...-xj75z  3468m CPU     208 MiB   (new pod, still booting)
```

The already-running pod's CPU jumped ~90x from idle (14m -> 1248m) once
it started actually processing forecast jobs (each one shells out to a
Python subprocess importing pandas/xgboost/scikit-learn, an
already-measured heavy cost). The **new pod booting** cost even more CPU
(3468m, i.e. ~3.5 real cores) than the already-warm pod actively doing
work, for JVM startup + Spring context + Flyway + JPA init alone, before
it has processed a single job. This is a concrete, real number behind
the worker replica scaling benchmark's finding: on a single-machine kind cluster, each new replica
briefly demands more CPU just to boot than an existing replica spends
doing real work, which is exactly the kind of contention that turned
"more replicas" into a net negative past 2 on this hardware.

## Failure recovery

Extends the local Kubernetes deployment's qualitative pod-delete check into a real timed
measurement (`measure_failure_recovery`,
`ml/.../kubernetes/benchmark.py`): delete the running backend pod,
time until the Deployment controller's replacement reports `1/1` Ready
again.

```text
recovery_seconds: 34.81
```

Consistent with the local Kubernetes deployment's own untimed observation (~47s) -- JVM boot +
Flyway + JPA + Redis/MinIO reconnection dominates either way; the
Deployment controller replaced the pod and the Service routed to it
again with no manual intervention, the same real property that document
already established, now with a number attached.

## Result artifact

```text
data/processed/benchmark/kubernetes_benchmark.json
```

Gitignored, regenerable like every other `data/processed/` artifact in
this project (`scripts/kubernetes/run_kubernetes_benchmark.py`).

## What this Kubernetes work as a whole found

A real, measured answer, the same bar the local distributed-execution
work set: Kubernetes correctly
provides self-healing (failure recovery) and can autoscale on a real
custom signal (Redis queue depth) without a full custom-
metrics pipeline. But "more replicas" is not free or even reliably
positive on a single-node local cluster -- it is bounded by real,
measured CPU contention (this benchmark's resource-usage numbers) that
the worker replica scaling benchmark already found turns into negative scaling past a small replica
count. `maxReplicaCount: 2` is a direct, evidence-based
consequence of that, not an arbitrary default.
