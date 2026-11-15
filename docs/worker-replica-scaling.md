# Worker Replica Scaling

This benchmark scales the `backend` Deployment (which serves the API and
also runs the worker, see `docs/kubernetes-manifests.md`) on the local
kind cluster and reports the results, including a result that goes
against expectations.

## Method

```text
Fixed workload: 8 identical forecast requests (the same region and
  cutoff as scripts/api/benchmark_forecast_api.py)
For each replica count in 1, 2, 4, 8:
  kubectl scale deployment/backend --replicas=<n>, wait until all pods are Ready
  send all 8 requests one after another
  poll every job until it reaches a final status (SUCCEEDED or FAILED)
  record the total wall-clock time and each job's completion time
```

`scripts/kubernetes/run_replica_scaling_benchmark.py` runs the
benchmark. `ml/.../kubernetes/replica_scaling.py` does the timing and
throughput arithmetic and is unit-tested with fakes
(`ml/tests/kubernetes/test_replica_scaling.py`). `ml/.../api/benchmark.py`
uses the same split for its sequential benchmark.

At the time, every job ended in the known FAILED state described in
`docs/clean-start-test.md` (the training split had only one class).
That does not affect this benchmark, which measures how fast replicas
empty the queue, not whether forecasts are correct. A FAILED job still
goes through the full path: dequeue, subprocess and result.

## Bug found: the liveness probe was too strict

The first scale-up to 4 replicas sent two of the four pods into a crash
loop. They were not stuck. The liveness probe in `backend.yaml`
(`initialDelaySeconds: 30`, `periodSeconds: 15` and the default
`failureThreshold: 3`, about 75 s in total) had been set from the
measured start-up time of a single replica (about 47 s). With four JVMs
starting at once (JVM start, Flyway, JPA, and the Redis and MinIO
connections all sharing the host CPU), some pods took longer than 75 s,
and kubelet killed and restarted them before they were ready.

The fix raises `failureThreshold` to 10 (about 180 s). The slowdown
comes from contention during scale-up and grows with load, so
`failureThreshold` is the right setting to change, not only a longer
`initialDelaySeconds`.

## Results

```text
replicas   total_wall_seconds   throughput_jobs_per_second
1          64.29                0.124
2          51.33                0.156
4          56.76                0.141
8          111.94               0.071
```

Per-job timings: `data/processed/benchmark/replica_scaling_benchmark.json`.

## Throughput peaks at 2 replicas, then falls below 1

Going from 1 to 2 replicas helps (+26% throughput), as expected when a
queue with one consumer gets two. More replicas do not help. Four
replicas are slower than two, and eight are slower than one (0.071
against 0.124 jobs/s, almost half). Individual jobs show the same: at 8
replicas the fastest job took 43 s and the slowest 90 s, both much
slower than the fastest job at 1 replica (16.5 s).

This is not a fairness bug in the queue. The Redis list pop is atomic,
so jobs do spread across the replicas that poll. The cause is what a
replica means here. Kind runs the whole cluster as one container on one
machine (12 cores, 16 threads, 16 GB RAM, checked with
`Win32_Processor` and `Win32_ComputerSystem`). Extra replicas compete
for the same hardware instead of getting their own, as they would on a
cluster with several nodes. Each replica is a full JVM, and each job
starts a Python interpreter through `ProcessBuilder` that imports
pandas, numpy, xgboost and scikit-learn.
`docs/bottleneck-identification.md` measured this start-and-import
cost and found that it outweighs the work itself; running more copies
at once does not make it smaller. At 8 replicas, up to 8 of these heavy
imports can start at once on the same 12 cores while 8 JVMs are also
running. This is the same cause found for `multiprocessing.Pool`
workers, now seen through a different mechanism (Kubernetes replicas
around a shared Redis queue instead of a local process pool) on the
same machine.

## What this means for autoscaling

Autoscaling on Redis queue depth needs a maximum replica count based on
this data, not a high number chosen at random: on this machine,
throughput only gets worse after 2 replicas. A production cluster with
several nodes may not have the same limit, because each node adds its
own hardware. But on the target tested here, "more replicas is always
better" is false.

## Out of scope

Autoscaler settings (minimum and maximum replicas, scale-up threshold,
scale-down behavior) are in `docs/autoscaling.md`. The full Kubernetes
benchmark is in `docs/kubernetes-benchmark.md`.
