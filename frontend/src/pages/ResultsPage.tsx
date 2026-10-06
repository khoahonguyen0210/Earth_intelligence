interface Result {
  headline: string;
  detail: string;
  source: string;
}

const RESULTS: Result[] = [
  {
    headline: "PR-AUC of 0.4513",
    detail: "XGBoost vs 0.2522 for the climatology baseline.",
    source: "docs/ml-benchmark.md",
  },
  {
    headline: "+0.081 PR-AUC from terrain",
    detail: "Elevation, slope, and land cover beat weather's +0.014.",
    source: "docs/ablation-benchmark.md",
  },
  {
    headline: "Well-calibrated probabilities",
    detail: "Predicted and observed fire frequency match to three decimals.",
    source: "docs/ml-benchmark.md",
  },
  {
    headline: "Zero lost tiles after a killed worker",
    detail: "Recovered in 1.353 seconds, 500 of 500 tiles present.",
    source: "docs/distributed-benchmark.md",
  },
  {
    headline: "100% planner accuracy",
    detail: "Intent, region, and execution right on 14 live questions.",
    source: "docs/planner-accuracy-benchmark.md",
  },
];

export function ResultsPage() {
  return (
    <>
      <header className="hero hero-compact">
        <span className="kicker">Results</span>
        <h1>What is measured</h1>
      </header>

      <main className="page page-prose">
        <p className="results-intro">
          Every number was run and recorded. Details live in <code>docs/</code>.
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
