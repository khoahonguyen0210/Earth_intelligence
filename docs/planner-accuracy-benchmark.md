# Final AI Planner Benchmark

This benchmark measures the planner on query count, intent, region and
time correctness, valid-plan rate and execution success. The first run
is described in `docs/planner-benchmark.md`. This run uses the same
frozen code, `planner/benchmark_set.py` and
`scripts/query/run_planner_benchmark.py` (both on the `benchmark-v1`
list), on the final version of the planner.

The earlier document warned that a second live run would not repeat the
same pattern exactly, because the LLM call is live and has no fixed
seed. That is what happened, and the result is reported as measured.

The question set later grew from 14 to 22 questions. That version is
reported in `docs/evaluation.md`.

## Result

A run against the live API (`gemini-3.1-flash-lite`, 14 fixed cases,
`data/processed/planner_benchmark/benchmark_report.json`):

```text
total_cases:                  14
intent_correctness:          1.0   (12/12 scored)
region_correctness:          1.0   (12/12 scored)
time_correctness:            0.667 (8/12 scored)
valid_plan_rate:             0.917 (11/12 scored, excludes ambiguous)
execution_success:           1.0   (14/14)
unsupported_request_handling: 0.5   (1/2)
```

The planner reached 100% intent and region correctness and 100%
execution success over 14 live queries. Every decision to plan or reject was
correct except one unsupported question that is open to more than one
reading.

## What changed since the first run

`time_correctness` fell from 1.0 in the first run to 0.667 here. Both
misses have the same cause. `count_california` asks for "between
2024-08-01 and 2024-08-10", and `count_bay_area` asks for "2024-07-01
and 2024-07-15". In this run, the model returned `end: "2024-08-11"` and
`end: "2024-07-16"`. It read the end date as inclusive and wrote a
correct half-open `[start, end)` range to cover it. The benchmark
compares `expected_time_range` by exact string, so a range one day
longer fails. This is a change in the model's output, not a scoring bug
like the region-name issue fixed after the first run. The first
document had said that a rerun "will very likely reproduce different
exact plan wording... but should reproduce the same category-level
pass/fail pattern". For this one metric, it did not.

The other five metrics and the one known miss repeated exactly. Intent
and region correctness are still 1.0, execution success is still 1.0,
and `valid_plan_rate` is still 0.917 with the same expected miss
(`ambiguous` cases are recorded as observed, not as pass or fail).
`unsupported_causal_question` ("Explain why California has so many
wildfires.") again received a `calculate_statistics` count plan instead
of a rejection. This is the same known limit: the planner turns a "why"
question into a nearby question that it can answer.

## Out of scope

- **The benchmark code is unchanged.** `planner/benchmark_set.py` and
  `scripts/query/run_planner_benchmark.py` are on the `benchmark-v1`
  frozen list, and this run only executes them.
- **The `time_correctness` drop is not treated as a bug.** The
  half-open range is correct behavior. The live run in
  `docs/ask-earth.md` saw the same thing, and the answer there said so
  openly instead of claiming an exact match. Making the check accept
  equivalent ranges, or steering the model toward one date convention,
  is future work.
