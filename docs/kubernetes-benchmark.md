# Kubernetes Benchmark

This benchmark records six measures on the local kind cluster: runtime,
throughput, speedup, efficiency, resource usage and failure recovery.
Where a measurement already exists, it is reused instead of measured
again.

## Runtime, throughput, speedup, efficiency

These are not measured again here. `docs/worker-replica-scaling.md`
already ran the fixed 8-job workload at 1, 2, 4 and 8 replicas on the
same cluster. A second sweep would only repeat it with normal noise
between runs. Speedup and efficiency are computed from those numbers
(`compute_speedup_efficiency` in `ml/.../kubernetes/replica_scaling.py`)
with the same formulas as `distributed/scaling.py`:
`speedup(n)=T1/Tn` and `efficiency(n)=speedup(n)/n`.

```text
replicas   runtime_s   throughput_jobs_per_s   speedup   efficiency
1           64.29      0.124                   1.000     1.000
2           51.33      0.156                   1.252     0.626
4           56.76      0.141                   1.133      0.283
8          111.94      0.071                   0.574     0.072
```

The conclusion is the same as in the replica scaling benchmark.
Efficiency drops steadily after 2 replicas, and 8 replicas are slower
than one (speedup below 1).

## Resource usage

Samples from `kubectl top pods`, at idle and during a KEDA scale-up
caused by 8 forecast requests (the autoscaler was not bypassed).
metrics-server was installed for this, because kind has none by
default, and patched with `--kubelet-insecure-tls`, the usual fix for
kind's self-signed kubelet certificates.

```text
idle, 1 replica:
  backend-...-44zh6    14m CPU     656 MiB

under load, during the scale-up to 2 replicas:
  backend-...-44zh6  1248m CPU     790 MiB   (the running pod, now processing jobs)
  backend-...-xj75z  3468m CPU     208 MiB   (the new pod, still starting)
```

The running pod's CPU rose about 90 times from idle (14m to 1248m) when
it began processing forecast jobs; each job starts a Python subprocess
that imports pandas, xgboost and scikit-learn, a cost measured earlier.
The **new pod used even more CPU** (3468m, about 3.5 cores) than the
running pod doing work, just for JVM start-up, the Spring context,
Flyway and JPA, before it processed a single job. This number supports
the replica scaling result: on a kind cluster on one machine, a new
replica briefly needs more CPU to start than an existing replica uses
for work. This contention is why adding replicas past 2 made things
worse on this hardware.

## Failure recovery

The local deployment checked pod replacement without timing it. Here it
is timed (`measure_failure_recovery` in `ml/.../kubernetes/benchmark.py`):
delete the running backend pod and measure the time until the
Deployment's replacement reports `1/1` Ready.

```text
recovery_seconds: 34.81
```

This agrees with the untimed observation in the local deployment (about
47 s). In both cases, JVM start-up, Flyway, JPA and the Redis and MinIO
connections take most of the time. The Deployment controller replaced
the pod, and the Service sent traffic to it again, with no manual step.

## Result file

```text
data/processed/benchmark/kubernetes_benchmark.json
```

Written by `scripts/kubernetes/run_kubernetes_benchmark.py`. Like every
file under `data/processed/`, it is ignored by git and can be rebuilt.

## Summary of the Kubernetes work

Kubernetes heals itself after a pod failure, and it can scale on a
custom signal (Redis queue depth) without a full custom metrics
pipeline. But more replicas are not free, and on a local cluster with
one node they do not reliably help. CPU contention, measured above,
limits them, and the replica scaling benchmark shows that this turns
into negative scaling after a small number of replicas. The setting
`maxReplicaCount: 2` follows directly from this evidence.
