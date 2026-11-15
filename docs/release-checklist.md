# Release Checklist

Each checked item below names the document, test or artifact that
shows it is done. The one unchecked item is stated as plainly as the
others.

## Product

```text
[x] Earth question works     docs/earth-intelligence-demo.md: a map
                             query on real data, with evidence,
                             inside the packaged container
[x] Forecast question works  docs/forecasting-demo.md: AI plan ->
                             validation -> workflow -> a SUCCEEDED
                             forecast at a documented cutoff
[x] Web UI works             docs/clean-start-test.md (Vite build,
                             200 at :5173); App.test.tsx and the
                             AskEarthForm and ForecastPanel tests
[x] Map works                ForecastMap.tsx and ForecastMap.test.tsx;
                             the FeatureCollection in
                             docs/earth-intelligence-demo.md
[x] Evidence works           every demo and benchmark document shows
                             an evidence block (dataset, region,
                             period, processing version)
```

## Data and science

```text
[x] Real Earth data          NASA FIRMS, ERA5-Land, Copernicus DEM
                             GLO-30, ESA WorldCover (README "Data")
[x] Provenance               data/provenance.py and the evidence block
                             in every result
[x] Validation               data/validation.py; the
                             *-input-contract.md documents
[x] California grid          data/grid.py, docs/california-grid-contract.md
[x] Leakage tests            ml/tests/forecast/test_leakage.py,
                             docs/scientific-regression-tests.md
[x] Fixed time split         forecast/spec.py (2019-2022/2023/2024),
                             docs/scientific-regression-tests.md
[x] Four-model benchmark     docs/ml-benchmark.md (climatology,
                             logistic regression, XGBoost and
                             calibrated XGBoost, all on full data)
[x] Calibration              the calibration table in
                             docs/ml-benchmark.md
[x] Ablations                docs/ablation-benchmark.md (weather,
                             geography)
[x] Reproducible artifacts   docs/reproducibility-package.md, run in
                             full in docs/clean-clone-test.md
```

## AI

```text
[x] Planner                  docs/natural-language-planner.md
[x] Deterministic validator  docs/plan-validator.md
[x] Approved tools only      planner/tools.py, docs/planner-tool-schemas.md
[x] Grounded answers         docs/grounded-answer-generation.md; every
                             Ask Earth demo answer cites its evidence
                             and never invents a number
[x] Planner benchmark        docs/planner-accuracy-benchmark.md (14
                             live cases, 100% intent, region and
                             execution)
```

## Backend and software engineering

```text
[x] Java/Spring API          backend/, docs/forecast-api-contract.md
[x] PostGIS                  docs/persistence-schema.md
[x] Redis                    docs/forecast-async-jobs.md
[x] Object storage           docs/object-storage-contract.md (MinIO/S3
                             put, get, exists and delete)
[x] Async jobs               docs/forecast-async-jobs.md
[x] Retries                  docs/forecast-retry-and-idempotency.md
[x] Timeouts                 forecast.python.timeout-seconds,
                             docs/forecast-retry-and-idempotency.md
[x] Idempotency              docs/forecast-retry-and-idempotency.md;
                             the duplicate-request scenario in
                             docs/reliability-tests.md (one row, one job)
[x] Unit, integration and    docs/unit-test-pass.md,
    end-to-end tests         docs/integration-test-pass.md,
                             docs/end-to-end-test-pass.md; 761 tests,
                             0 failures, run again from a clean clone
                             in docs/clean-clone-test.md
```

## Distributed and cloud

```text
[x] Local distributed        docs/one-worker-baseline.md,
    execution                docs/multi-worker-scaling.md
[x] Distributed benchmark    docs/distributed-benchmark.md, reproduced
                             separately twice
                             (docs/distributed-result-demo.md)
[x] Docker                   docs/docker-images.md,
                             docs/docker-compose-stack.md
[x] Kubernetes               docs/kubernetes-manifests.md,
                             docs/local-kubernetes-deployment.md;
                             checked live on a kind cluster
[x] AWS                      docs/cloud-deployment.md: a specific
                             target (EKS 1.36, RDS, ElastiCache, S3,
                             ALB), not just a name
[x] Terraform                docs/terraform-layout.md: modules,
                             `terraform fmt` and `validate` pass, Trivy
                             clean
[ ] Cloud benchmark          Not done. This would run the same
                             benchmark workload on AWS (runtime,
                             throughput, resource use, approximate
                             cost, errors). The Terraform was never
                             applied to an AWS account, because a demo
                             deployment costs about $0.40 per hour
                             (docs/cloud-deployment.md,
                             docs/terraform-layout.md). So there are
                             no measured cloud runtime or cost
                             numbers, only the design's cost estimate
                             (about $290/month). This item is reported
                             as missing instead of being filled with a
                             simulated number.
```

## Reliability and security

```text
[x] Logs                     docs/structured-logging.md
[x] Metrics                  docs/metrics.md
[x] Traces                   docs/tracing.md
[x] Failure tests            docs/reliability-tests.md,
                             docs/fault-injection-test.md (killed
                             processes and stopped containers)
[x] Recovery evidence        docs/reliability-tests.md,
                             docs/distributed-benchmark.md (a killed
                             worker, 500/500 tiles recovered, 1.353s)
[x] Secrets protected        docs/security-baseline.md (redaction,
                             dependency and secret scanning in CI)
[x] Input and tool           docs/plan-validator.md, RequestShape
    validation               (docs/security-baseline.md),
                             planner-tool-schemas.md
```

## Results

```text
[x] ML result                docs/ml-benchmark.md: PR-AUC 0.4513
[x] Processing-time result   docs/ml-benchmark.md (training and
                             inference time),
                             docs/bottleneck-identification.md
[x] Distributed result       docs/distributed-benchmark.md
[x] AI planner result        docs/planner-accuracy-benchmark.md
[x] Reliability result       docs/reliability-tests.md,
                             docs/distributed-benchmark.md
[x] Reproducible benchmark   docs/reproducibility-package.md,
    artifacts                docs/portfolio/benchmark-results.{json,csv}
[x] Headline results use     docs/headline-results.md: every headline
    only measured numbers    is copied from a measured number
```

## Score: 48 / 49

The one missing item is a cloud benchmark on live AWS infrastructure. It
was left out on purpose to avoid the cost. Every other item has a
document or artifact behind it. The repository contains code, a
working product, tests, scientific experiments, benchmarks, measured
results, reproducibility and documentation. The one gap is a single
benchmark (a run on the cloud), not a missing category.
