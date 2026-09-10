# Final Benchmark Freeze — LOCKED

This document records Task 16.1, the first task of Phase 16. It is not
a brainstorming document.

Task 16.1 asks for the benchmark code to be frozen -- a Git tag/commit
marking the exact version that produces Phase 16's headline numbers
(Tasks 16.2-16.5), so those numbers stay reproducible: the same code,
run again, must produce the same measurement. Nothing below is frozen
because it is finished being *developed* -- it is frozen because from
this point on, changing it invalidates any number already measured
against it, per the handbook's own rule: don't change benchmark code
after freezing without versioning a new benchmark.

**Tag:** `benchmark-v1`, on commit `ae0306f` (this doc's own commit --
the tag is created immediately after this doc is committed, pointing at
it).

## What is frozen, and why exactly this set

Frozen: the *evaluation harnesses* Tasks 16.2-16.5 run to produce a
number, not the systems under measurement. The model, the distributed
runner, and the planner itself all keep evolving independently and are
governed by their own locks (`docs/feature-set-freeze.md`,
`docs/scientific-regression-tests.md`, `docs/distributed-workload.md`);
re-running these harnesses against a later, improved system is exactly
the point -- what must not silently drift is *how the number is
computed*.

```text
16.2 Final ML benchmark
    ml/src/.../models/benchmark.py       run_baseline_benchmark: the
                                          Climatology/LogReg/XGBoost/
                                          Calibrated-XGBoost comparison
    ml/src/.../models/harness.py         run_experiment_on_rows,
                                          SUPPORTED_MODELS -- what
                                          benchmark.py calls per model
    scripts/models/run_final_benchmark.py the real-dataset runner

16.3 Final ablation benchmark
    ml/src/.../models/ablation.py        run_weather_ablation /
                                          run_geography_ablation:
                                          fire-history-only vs +weather
                                          vs +weather+geography
    scripts/models/run_weather_ablation.py
    scripts/models/run_geography_ablation.py

16.4 Final distributed benchmark
    ml/src/.../distributed/scaling.py    run_scaling_benchmark, the
                                          locked WORKER_COUNTS (1/2/4/8)
    ml/src/.../distributed/run.py        run_distributed_inference /
                                          prepare_run_context -- what
                                          scaling.py drives per worker
                                          count
    ml/src/.../distributed/fault_tolerance.py  the crash-injection this
                                          benchmark's failure/recovery
                                          column measures
    scripts/distributed/run_scaling_benchmark.py

16.5 Final AI planner benchmark
    ml/src/.../planner/benchmark_set.py  CATEGORIES, BenchmarkCase,
                                          score_case, summarize -- the
                                          seven-category scoring rubric
    scripts/query/run_planner_benchmark.py
```

**Deliberately not re-frozen here:**
`ml/src/.../distributed/workload.py` (Task 9.1 already froze this --
the fixed input the benchmark measures, not the measuring code itself);
`ml/src/.../models/xgboost_model.py` / `calibration.py` /
`preprocessing.py` / `metrics.py` and `ml/src/.../planner/generate_plan.py`
(the actual model and planner -- Task 15.4 and earlier freezes already
lock their correctness properties; Phase 16 exists to measure them, not
to re-lock them a second time under a different name).

## The rule this freeze enforces

Any change to a file listed above, after `benchmark-v1`, needs a new
tag (`benchmark-v2`, ...) before its output is reported as a headline
number. A bug fix to the harness itself (as opposed to the system it
measures) is exactly the kind of change that requires this -- it would
silently change what "PR-AUC" or "speedup" means without changing the
number honestly.
