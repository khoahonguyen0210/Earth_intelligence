import { Link } from "react-router-dom";

export function AboutPage() {
  return (
    <>
      <header className="hero hero-compact">
        <span className="kicker">About</span>
        <h1>What this is, and how it works</h1>
      </header>

      <main className="page page-prose">
        <section>
          <h2>What it is</h2>
          <p>
            A web-based Earth intelligence platform: a user asks a natural-language
            question about Earth, and the system identifies the geographic and temporal
            scope, retrieves the required Earth data, executes a validated analysis
            workflow, and returns an evidence-backed answer, never a fabricated
            one. Forecasting is one capability used to validate the platform&rsquo;s
            scientific and computational depth, not the whole product.
          </p>
        </section>

        <section>
          <h2>The problem</h2>
          <p>
            The flagship capability is a locked scientific problem: 24-hour wildfire
            occurrence-risk forecasting on a fixed California 0.1&deg; grid, using public
            Earth-observation, weather, and geographic data. For each grid cell at each
            hourly cutoff, the target is <code>1</code> if at least one qualifying NASA
            FIRMS active-fire observation occurs in that cell during the next 24 hours,
            and <code>0</code> otherwise. A feature may only use information available at
            or before its own cutoff, enforced by a dedicated test suite, not just
            convention.
          </p>
        </section>

        <section>
          <h2>How a question actually gets answered</h2>
          <ol className="pipeline-list">
            <li>An LLM planner turns the question into a structured, typed plan,
              never free-form code.</li>
            <li>A deterministic validator rejects an invalid plan before a single step
              executes. The LLM cannot bypass this gate.</li>
            <li>The validated plan runs against real Earth data (fire history, weather,
              geography) and a real trained forecasting model.</li>
            <li>The answer comes back with its evidence attached: dataset, time range,
              region, model version, and calibration: every number traceable to
              what actually produced it.</li>
          </ol>
        </section>

        <section>
          <h2>The science</h2>
          <p>
            The main benchmark is a locked ladder of four models: Climatology,
            Logistic Regression, XGBoost, and Calibrated XGBoost, scored on
            PR-AUC, ROC-AUC, Brier score, log loss, and calibration. Accuracy is
            deliberately not used as a metric: it&rsquo;s the wrong measure for a class
            this imbalanced (wildfires are rare). See the <Link to="/results">Results</Link>{" "}
            page for what was actually measured.
          </p>
        </section>
      </main>
    </>
  );
}
