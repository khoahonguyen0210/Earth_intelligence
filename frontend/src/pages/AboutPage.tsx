import { Link } from "react-router-dom";

export function AboutPage() {
  return (
    <>
      <header className="hero hero-compact">
        <span className="kicker">About</span>
        <h1>How it works</h1>
      </header>

      <main className="page page-prose">
        <section>
          <h2>What it is</h2>
          <p>
            Ask a question about Earth in plain English and get an answer backed by
            real data and a trained model.
          </p>
        </section>

        <section>
          <h2>The forecast</h2>
          <p>
            Will a fire start in the next 24 hours? Each cell of a 0.1&deg; California
            grid gets a risk score, using only information available at the cutoff.
          </p>
        </section>

        <section>
          <h2>The pipeline</h2>
          <ol className="pipeline-list">
            <li>An LLM turns the question into a typed plan.</li>
            <li>A validator rejects any invalid plan.</li>
            <li>The plan runs on real data and a trained model.</li>
            <li>The answer returns with its evidence attached.</li>
          </ol>
        </section>

        <section>
          <h2>The benchmark</h2>
          <p>
            Four models, from climatology to calibrated XGBoost, scored on PR-AUC
            because wildfires are rare. See <Link to="/results">Results</Link>.
          </p>
        </section>
      </main>
    </>
  );
}
