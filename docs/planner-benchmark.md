# Planner Benchmark — LOCKED

This document freezes the AI planner benchmark. It is not a brainstorming
document. It measures `docs/natural-language-planner.md` and
`docs/plan-validator.md` as already built, rather than adding
to either.

## Workload (fixed)

```text
14 fixed natural-language questions, 2 per handbook category:
  count, trend, compare, map, forecast, ambiguous, unsupported
provider:  Gemini (docs/natural-language-planner.md's provider note)
model:     ai_earth_intelligence_and_forecasting_engine.planner.generate_plan.MODEL
call:      one live generate_plan(question, client) per case -- the
           real pipeline (LLM -> structured plan -> validator),
           not a mock
```

`compare` has no dedicated tool in the tool surface: a correct
answer to a compare question is two or more `calculate_statistics`/
`generate_map` steps naming different regions, which is what
`BenchmarkCase.min_matching_steps` checks for.

`ambiguous` cases (missing region/time, or a genuinely vague question)
have no single correct outcome to assert -- the planner could reasonably
either reject them or guess a default. They are run and recorded for
observability, but never scored pass/fail, unlike every other category.

## Metric (fixed)

```text
intent_correctness            -- did a produced plan use one of the
                                  question's expected tool(s)?
region_correctness             -- did a produced plan name the expected
                                  region(s)?
time_correctness                -- did a produced plan carry the
                                  question's exact stated time_range?
valid_plan_rate                  -- did the observed outcome (plan
                                  produced vs. rejected) match what the
                                  case expects? (excludes ambiguous
                                  cases, which expect neither)
execution_success                 -- did the pipeline complete without an
                                  unexpected failure? (a validator
                                  rejection or a model refusal are both
                                  `generate_plan`'s documented, handled
                                  ValueError outcomes -- only anything
                                  else, e.g. a network error, counts
                                  against this)
unsupported_request_handling       -- valid_plan_rate restricted to the
                                  "unsupported" category alone
```

Each rate is computed over however many cases actually have that metric
scored (e.g. `time_correctness` excludes the two `forecast` cases, which
carry a `cutoff` rather than a `time_range`) -- a case with nothing fixed
to check contributes nothing to a rate's denominator, it is not counted
as a failure.

Region correctness normalizes a plan's raw region string exactly the
way `query.region._normalize_named` does (lowercase, spaces to
underscores) before comparing: the real validator accepts `"Bay Area"`
exactly as it accepts `"bay_area"`, so scoring on the raw string would
flag a plan the real system already accepts as wrong. This was a genuine
scoring bug caught and fixed against a real live run, not a hypothetical
-- the first live run measured `region_correctness: 0.4` from this
mismatch alone; fixing the scoring function's normalization (not the
planner) brought it to `1.0` with the identical plans.

## Result

```text
ml/src/.../planner/benchmark_set.py   -- BENCHMARK_CASES / score_case /
                                          summarize (unit-tested against
                                          synthetic Plan/error values,
                                          never a live call --
                                          tests/planner/test_benchmark_set.py)
scripts/query/run_planner_benchmark.py -- thin driver: real generate_plan
                                          calls against a real genai.Client,
                                          not unit-tested itself, same as
                                          every other real-caller script
                                          under scripts/
data/processed/planner_benchmark/benchmark_report.json
                                       -- raw per-case results + the
                                          summary rates (one file).
                                          Gitignored, a regenerable local
                                          artifact like the forecast API
                                          benchmark's own forecast_api_benchmark.json.
```

A real run against the live API (`gemini-3.1-flash-lite`, 14 cases):

```text
intent_correctness:          1.0   (12/12 scored)
region_correctness:          1.0   (12/12 scored)
time_correctness:            1.0   (10/10 scored -- excludes forecast)
valid_plan_rate:             0.917 (11/12 scored -- excludes ambiguous)
execution_success:           1.0   (14/14)
unsupported_request_handling: 0.5   (1/2)
```

The one miss: `unsupported_causal_question` ("Explain why California
has so many wildfires.") did not get rejected -- the model answered it
with a `calculate_statistics` count plan instead of recognizing that no
tool here answers a causal "why" question. This is a real, measured
planner limitation, not a validator gap: the produced plan is
structurally valid (a real region, a real time range, a real tool), so
the validator correctly accepts it -- the mismatch is the model silently
reinterpreting an unanswerable question as an adjacent answerable one
rather than saying it cannot answer. Fixing this (e.g. a stronger system
prompt instruction, or a larger model) is future tuning work this task's
job was to surface, not to resolve.

## What this document does not define

This is a measurement, not a certification gate: there is no "must pass"
threshold enforced anywhere, matching the handbook's Benchmark-task
definition of done (fixed workload, explicit metric, repeatable runs,
raw result saved, summary generated) rather than the Code-task one.
Re-running the script will very likely reproduce different exact plan
wording -- the LLM call is real and not seeded -- but should reproduce
the same category-level pass/fail pattern against the same model.
Improving on the one measured miss, adding more cases, or scoring a
"clarification requested" outcome distinctly from an outright rejection
are all future work; this task's job was only to build the fixed
benchmark and record one real, honest result from it.
