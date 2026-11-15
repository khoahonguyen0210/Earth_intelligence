# Final Benchmark Freeze

The benchmark code is frozen at a Git tag that marks the exact version
behind the headline numbers (the final ML, ablation, distributed and AI
planner benchmarks). Running the same code again must give the same
measurement. The code is not frozen because it is finished. It is
frozen because any change from now on would make the numbers already
measured with it invalid. The rule is: do not change benchmark code
after the freeze without creating a new benchmark version.

**Tag:** `benchmark-v1`, on the commit that added this document.

## What is frozen

The frozen code is the evaluation code that produces each number, not
the systems being measured. The model, the distributed runner and the
planner can keep changing, under their own rules
(`docs/feature-set-freeze.md`, `docs/scientific-regression-tests.md`,
`docs/distributed-workload.md`). Running this frozen code on a later,
better system is the purpose of the freeze. What must not change
quietly is how each number is computed.

```text
Final ML benchmark
    ml/src/.../models/benchmark.py       run_baseline_benchmark: the
                                         Climatology/LogReg/XGBoost/
                                         Calibrated-XGBoost comparison
    ml/src/.../models/harness.py         run_experiment_on_rows and
                                         SUPPORTED_MODELS, which
                                         benchmark.py calls per model
    scripts/models/run_baseline_benchmark.py the full-dataset runner

Final ablation benchmark
    ml/src/.../models/ablation.py        run_weather_ablation and
                                         run_geography_ablation:
                                         fire history only, +weather,
                                         +weather+geography
    scripts/models/run_weather_ablation.py
    scripts/models/run_geography_ablation.py

Final distributed benchmark
    ml/src/.../distributed/scaling.py    run_scaling_benchmark and the
                                         fixed WORKER_COUNTS (1/2/4/8)
    ml/src/.../distributed/run.py        run_distributed_inference and
                                         prepare_run_context, which
                                         scaling.py runs per worker
                                         count
    ml/src/.../distributed/fault_tolerance.py  the crash injection
                                         behind the failure and
                                         recovery column
    scripts/distributed/run_scaling_benchmark.py

Final AI planner benchmark
    ml/src/.../planner/benchmark_set.py  CATEGORIES, BenchmarkCase,
                                         score_case and summarize: the
                                         scoring rules for the seven
                                         categories
    scripts/query/run_planner_benchmark.py
```

**Not included on purpose:**
`ml/src/.../distributed/workload.py` is frozen elsewhere; it is the
fixed input that the benchmark measures, not the measuring code.
`ml/src/.../models/xgboost_model.py`, `calibration.py`,
`preprocessing.py`, `metrics.py` and `ml/src/.../planner/generate_plan.py`
are the model and the planner themselves. Earlier freezes already fix
their correctness; the benchmarks measure them and do not freeze them a
second time.

## Rule

Any change to a file listed above after `benchmark-v1` needs a new tag
(`benchmark-v2` and so on) before its output is reported as a headline
number. This includes a bug fix in the benchmark code itself, as
opposed to the system it measures, because such a fix would change what
"PR-AUC" or "speedup" means while the number appears unchanged.
