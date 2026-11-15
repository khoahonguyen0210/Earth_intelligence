# Headline Results

These are the main results from the final benchmarks. Each one was
measured and can be reproduced. Every number is copied unchanged from
its source document.

## The five headline results

**XGBoost reached a PR-AUC of 0.4513, nearly double the 0.2522 of
climatology.** It was trained on the full feature set using the
2019-2022 California fire history and weather record (877,800 rows,
88 weekly cutoffs).
Source: `docs/ml-benchmark.md`.

**Terrain and land-cover features raised PR-AUC by +0.081 (0.370 ->
0.451).** Elevation, slope and the ESA WorldCover class were added on
top of fire history and weather. Their gain is more than five times the
+0.014 that weather added.
Source: `docs/ablation-benchmark.md`.

**The probabilities are well calibrated.** In the near-zero bin, which
holds 218,223 of the 219,450 test rows, predicted and observed fire
frequency agree to three decimal places (0.0018 and 0.0012). XGBoost was
calibrated with isotonic regression on the validation split before it
was evaluated on the held-out test split.
Source: `docs/ml-benchmark.md`.

**No tiles were lost after a worker was killed.** The run recovered in
1.353 seconds with all 500/500 tiles present. A per-chunk timeout
detects the failure, and only the lost chunk is retried on the same
worker pool; finished chunks are not run again.
Source: `docs/distributed-benchmark.md`.

**The planner reached 100% intent correctness, 100% region correctness
and 100% execution success on 14 questions against the live Gemini
API.** Every plan is checked against the backend tool schema before any
step runs.
Source: `docs/planner-accuracy-benchmark.md`. The later 22-question
version is in `docs/evaluation.md`.

## Measured results not chosen as headlines

Some results are limits or mixed findings, so they are not headlines.
They are documented in their source documents and listed here so that
nothing is hidden:

```text
weather's mixed effect           +0.0144 PR-AUC but -0.0117 ROC-AUC when
                                 added to fire history alone. The effect
                                 is reproducible but small and mixed.
                                 docs/ablation-benchmark.md

more workers = slower            1, 2, 4 and 8 workers get steadily
                                 slower on this Windows/spawn platform
                                 (587 -> 22 tiles/s). This repeats the
                                 first scaling result, but it is a
                                 platform limit, not an achievement.
                                 docs/distributed-benchmark.md

"why" question miss              "Explain why California has so many
                                 wildfires" got a count plan instead of
                                 a rejection, in both the first and the
                                 final run. A known limit.
                                 docs/planner-accuracy-benchmark.md

time_correctness changes         fell from 1.0 to 0.667 between the
  between runs                   first and final planner runs, because
                                 the live model chose a different
                                 date-range convention, not because of
                                 a code change. A result that changes
                                 between runs cannot be a headline.
                                 docs/planner-accuracy-benchmark.md
```

## Rules followed

- **No number is invented, rounded up or partly quoted.** Every value
  above appears as written in its source document, which in turn copies
  the benchmark script's output.
- **Only the final benchmarks are used.** Other results, such as the
  API latency and Kubernetes benchmarks, are reported in their own
  documents and in the README.
