interface Result {
  headline: string;
  detail: string;
  source: string;
}

// Copied verbatim from docs/headline-results.md: real, measured,
// reproducible numbers, never invented for this page.
const RESULTS: Result[] = [
  {
    headline: "Achieved a PR-AUC of 0.4513 with XGBoost",
    detail:
      "Nearly double climatology's 0.2522 baseline, by training the locked feature set on the real 2019-2022 California fire history and weather record (877,800 rows, 88 weekly cutoffs).",
    source: "docs/ml-benchmark.md",
  },
  {
    headline: "Achieved a PR-AUC gain of +0.081 from geography features",
    detail:
      "Adding real terrain and land-cover features (elevation, slope, land cover) on top of fire history and weather, more than five times weather's own +0.014 contribution.",
    source: "docs/ablation-benchmark.md",
  },
  {
    headline: "Achieved well-calibrated probabilities",
    detail:
      "Predicted and observed fire frequency matching to three decimal places across the dominant near-zero bin (218,223 of 219,450 real test rows), by isotonic-calibrating XGBoost on the validation split.",
    source: "docs/ml-benchmark.md",
  },
  {
    headline: "Zero lost tiles after a real killed worker",
    detail:
      "Recovered in 1.353 seconds, with 500/500 tiles present at completion, by detecting the failure via a per-chunk timeout and retrying only the lost chunk against the same worker pool.",
    source: "docs/distributed-benchmark.md",
  },
  {
    headline: "100% intent correctness, 100% region correctness, 100% execution success",
    detail:
      "Across 14 real natural-language questions against the live Gemini API, by validating every planner-produced plan against the real backend tool schema before any step executes.",
    source: "docs/planner-accuracy-benchmark.md",
  },
];

export function ResultsPage() {
  return (
    <>
      <header className="hero hero-compact">
        <span className="kicker">Results</span>
        <h1>Real, measured, reproducible</h1>
      </header>

      <main className="page page-prose">
        <p className="results-intro">
          Every number below was actually run and recorded: not estimated, not
          rounded favorably, not cherry-picked. Full detail, raw benchmark data, and the
          exact commands to reproduce each one live in this project&rsquo;s own{" "}
          <code>docs/</code> folder.
        </p>

        <ul className="results-list">
          {RESULTS.map((result) => (
            <li key={result.headline}>
              <p className="result-headline">{result.headline}</p>
              <p className="result-detail">{result.detail}</p>
              <p className="result-source">{result.source}</p>
            </li>
          ))}
        </ul>
      </main>
    </>
  );
}
