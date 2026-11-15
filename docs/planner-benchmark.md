# Planner Benchmark

This benchmark measures the planner (`docs/natural-language-planner.md`)
and the plan validator (`docs/plan-validator.md`) as they are built. It
does not change either one.

## Workload

```text
14 fixed natural-language questions, 2 per category:
  count, trend, compare, map, forecast, ambiguous, unsupported
provider:  Gemini (see the provider note in docs/natural-language-planner.md)
model:     ai_earth_intelligence_and_forecasting_engine.planner.generate_plan.MODEL
call:      one live generate_plan(question, client) per case: the full
           pipeline (LLM -> structured plan -> validator), not a mock
```

There is no separate tool for `compare`. A correct answer to a compare
question is two or more `calculate_statistics` or `generate_map` steps
with different regions. `BenchmarkCase.min_matching_steps` checks for
this.

`ambiguous` cases (a missing region or time, or a vague question) have
no single correct outcome. The planner could reasonably reject them or
choose a default. They are run and recorded, but unlike every other
category they are never scored as pass or fail.

## Metrics

```text
intent_correctness            did a produced plan use one of the
                              question's expected tools?
region_correctness            did a produced plan name the expected
                              regions?
time_correctness              did a produced plan carry the
                              question's exact stated time_range?
valid_plan_rate               did the outcome (plan produced or
                              rejected) match what the case expects?
                              (excludes ambiguous cases, which expect
                              neither)
execution_success             did the pipeline finish without an
                              unexpected failure? (a validator
                              rejection and a model refusal are both
                              handled ValueError outcomes of
                              generate_plan; anything else, such as a
                              network error, counts against this)
unsupported_request_handling  valid_plan_rate for the "unsupported"
                              category only
```

Each rate is computed over the cases that have that metric. For
example, `time_correctness` leaves out the two `forecast` cases, which
have a `cutoff` instead of a `time_range`. A case with nothing to check
is left out of the denominator; it does not count as a failure.

Before comparing regions, the score normalizes the plan's region string
in the same way as `query.region._normalize_named` (lowercase, spaces to
underscores). The validator accepts `"Bay Area"` just as it accepts
`"bay_area"`, so scoring on the raw string would mark a valid plan as
wrong. The first live run found this bug: it measured
`region_correctness: 0.4` from this mismatch alone. Fixing the scoring
function, not the planner, raised it to `1.0` with the same plans.

## Files

```text
ml/src/.../planner/benchmark_set.py      BENCHMARK_CASES, score_case and
                                         summarize; unit-tested with
                                         synthetic Plan and error values,
                                         never a live call
                                         (tests/planner/test_benchmark_set.py)
scripts/query/run_planner_benchmark.py   thin driver that calls
                                         generate_plan with a genai.Client;
                                         not unit-tested, like the other
                                         scripts under scripts/
data/processed/planner_benchmark/benchmark_report.json
                                         raw per-case results and the
                                         summary rates in one file; ignored
                                         by git and can be rebuilt, like
                                         forecast_api_benchmark.json
```

## Result

A run against the live API (`gemini-3.1-flash-lite`, 14 cases):

```text
intent_correctness:          1.0   (12/12 scored)
region_correctness:          1.0   (12/12 scored)
time_correctness:            1.0   (10/10 scored, excludes forecast)
valid_plan_rate:             0.917 (11/12 scored, excludes ambiguous)
execution_success:           1.0   (14/14)
unsupported_request_handling: 0.5   (1/2)
```

The one miss: `unsupported_causal_question` ("Explain why California
has so many wildfires.") was not rejected. The model answered it with a
`calculate_statistics` count plan instead of seeing that no tool can
answer a "why" question. This is a limit of the planner, not a gap in
the validator. The plan is valid in structure (a known region, a time
range and an existing tool), so the validator accepts it. The problem
is that the model quietly turns a question it cannot answer into a
nearby one it can. A stronger instruction in the system prompt or a
larger model might fix this; that is future work.

## Limits

This is a measurement, not a gate. No pass threshold is enforced. A
rerun will very likely produce different plan wording, because the LLM
call is live and has no fixed seed, but it should produce the same
pass and fail pattern by category with the same model. Fixing the one
miss, adding cases, and scoring "asked for clarification" apart from
"rejected" are future work.
