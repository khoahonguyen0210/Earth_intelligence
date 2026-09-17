# Worker Replica Scaling — LOCKED

This document freezes the worker replica scaling benchmark. It is not
a brainstorming document. It scales `backend`'s Deployment (the folded
backend+worker role, `docs/kubernetes-manifests.md`) against the real
kind cluster already deployed, and reports what actually happened --
including a real, counter-intuitive negative result, the same honesty
bar already set for distributed execution.

## Method

```text
Fixed workload: 8 identical forecast requests (same region/cutoff
  scripts/api/benchmark_forecast_api.py already uses)
For each replica count in 1, 2, 4, 8:
  kubectl scale deployment/backend --replicas=<n>, wait for all pods Ready
  submit all 8 requests back to back
  poll every job until it reaches a terminal status (SUCCEEDED or FAILED)
  record total wall-clock time and per-job completion time
```

`scripts/kubernetes/run_replica_scaling_benchmark.py` is the real
caller; `ml/.../kubernetes/replica_scaling.py` owns the timing/
throughput arithmetic (unit-tested against fakes,
`ml/tests/kubernetes/test_replica_scaling.py`), the same split
`ml/.../api/benchmark.py` already uses for its own sequential
benchmark. Every job reaches the same real, already-documented FAILED
(`docs/clean-start-test.md`'s single-class training-split gap) -- that
is fine here, since this benchmark measures queue-drain throughput
across replicas, not forecast correctness, and a FAILED result still
exercises the full dequeue -> subprocess -> result pipeline.

## A real bug this task found: the liveness probe was too aggressive

Scaling to 4 replicas for the first time crash-looped two of the four
pods -- not because they were stuck, but because `backend.yaml`'s
liveness probe (`initialDelaySeconds: 30`, `periodSeconds: 15`, the
default `failureThreshold: 3`, so ~75s total tolerance) was tuned
against the single-replica boot time already measured (~47s). With four JVMs
booting at once (JVM start, Flyway, JPA, Redis/MinIO connect all
contending for the same host CPU), some pods took longer than 75s and
were killed and restarted mid-boot by kubelet before they ever became
ready. Fixed by raising `failureThreshold` to 10 (~180s tolerance) --
the slowdown under real concurrent scale-up is genuine contention, not
a one-time fixed delay, so `failureThreshold` (which scales with load)
is the correct probe knob, not just a bigger `initialDelaySeconds`.

## Results

```text
replicas   total_wall_seconds   throughput_jobs_per_second
1          64.29                0.124
2          51.33                0.156
4          56.76                0.141
8          111.94               0.071
```

Full per-job timings: `data/processed/benchmark/replica_scaling_benchmark.json`.

## The real, counter-intuitive finding: throughput peaks at 2 replicas, then gets worse than 1

Going from 1 to 2 replicas helps (+26% throughput) -- exactly what
splitting a single-consumer queue across two consumers should do. Going
further does not: 4 replicas is worse than 2, and 8 replicas is worse
than even the single-replica baseline (0.071 vs 0.124 jobs/s -- almost
half the throughput, not more). Individual job times make this
concrete: at 8 replicas the fastest job still took 43s and the slowest
90s, both far worse than 1 replica's own fastest job (16.5s).

This is not a queue-fairness bug -- Redis's list pop is atomic, so jobs
really do spread across whichever replicas are polling. The real cause
is what "replica" means on this deployment target specifically: `kind`
runs the entire cluster as one container on one physical machine (12
cores / 16 threads, 16GB RAM, confirmed via `Win32_Processor`/
`Win32_ComputerSystem`). Kubernetes replicas here add contention for
that one fixed pool of real hardware, not independent hardware the way
replicas would on a real multi-node cluster. Each replica is a full JVM
plus, per job, a `ProcessBuilder` subprocess that starts a Python
interpreter and imports pandas/numpy/xgboost/scikit-learn --
`docs/bottleneck-identification.md` already measured that
exact spawn-and-import cost directly and found it dominates real
per-unit work, non-parallelizable overhead that does not shrink no
matter how many workers run it concurrently. At 8 replicas, up to 8 of
those heavy imports can be starting at once on the same 12 real cores
while 8 JVMs are also live -- the same root cause already
identified for `multiprocessing.Pool` workers, now reproduced in a
completely different mechanism (Kubernetes Deployment replicas around a
shared Redis queue instead of a local process pool), on the same real
machine.

## What this means for autoscaling

Configuring autoscaling on Redis queue depth needs a real
maximum-replica ceiling informed by this data, not an arbitrarily high
one: this benchmark's own machine gets strictly worse past 2 replicas.
A production multi-node cluster would not necessarily hit the same
ceiling (real independent hardware per node changes the math), but
"more replicas is always better" is empirically false on the target
this task actually had to verify against.

## What this document does not define

Configuring the actual autoscaler (min/max replicas, scale-up
threshold, scale-down behavior) is one later task. Running the full
Kubernetes benchmark suite is another.
