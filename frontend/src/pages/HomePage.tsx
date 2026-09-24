import { useState } from "react";
import { Link } from "react-router-dom";
import { createEarthQuery, getEarthQueryResult } from "../api/client";
import type { EarthQueryResult } from "../api/types";
import { AskEarthForm } from "../components/AskEarthForm";
import { EarthQueryResultView } from "../components/EarthQueryResultView";
import { EmberField } from "../components/EmberField";
import { ForecastPanel } from "../components/ForecastPanel";import { useCountUp } from "../hooks/useCountUp";

type Status = "idle" | "loading" | "error" | "success";

const STATS = [
  { value: "0.45", label: "PR-AUC" },
  { value: "100%", label: "planner success" },
  { value: "1.35s", label: "worker recovery" },
  { value: "4", label: "data sources" },
];

const FEATURES = [
  {
    title: "Ask in plain English",
    body: "An LLM plans, a validator checks, then it runs.",
  },
  {
    title: "24-hour wildfire risk",
    body: "Calibrated XGBoost on California fire, weather, and terrain data.",
  },
  {
    title: "Every answer has evidence",
    body: "Dataset, region, period, and model version on every result.",
  },
];

function Stat({ value, label }: { value: string; label: string }) {
  const { ref, display } = useCountUp<HTMLElement>(value);

  return (
    <div>
      <strong ref={ref}>{display}</strong>
      <span>{label}</span>
    </div>
  );
}

export function HomePage() {
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<EarthQueryResult | null>(null);

  async function handleAsk(question: string) {
    setStatus("loading");
    setError(null);
    setResult(null);

    try {
      const summary = await createEarthQuery(question);
      const resultResponse = await getEarthQueryResult(summary.id);
      setResult(resultResponse.result);
      setStatus("success");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
      setStatus("error");
    }
  }

  return (
    <>
      <header className="hero">
        <EmberField />
        <span className="kicker">Earth intelligence</span>
        <h1>Ask Earth.</h1>
        <p className="hero-sub">Plain-English questions about our planet, answered from real satellite data with the evidence shown.</p>
        <div className="hero-cta">
          <a href="#ask-earth" className="btn-primary">
            Ask Earth a question
          </a>
          <Link to="/results" className="btn-secondary">
            Results &rarr;
          </Link>
        </div>
      </header>

      <section className="stats-strip" aria-label="Measured results">
        {STATS.map((stat) => (
          <Stat key={stat.label} value={stat.value} label={stat.label} />
        ))}
      </section>

      <section className="feature-grid" aria-label="What this does">
        {FEATURES.map((feature) => (
          <div key={feature.title}>
            <h3>{feature.title}</h3>
            <p>{feature.body}</p>
          </div>
        ))}
      </section>

      <main className="page" id="ask-earth">
        <AskEarthForm onSubmit={handleAsk} disabled={status === "loading"} />

        {status === "loading" && <p role="status">Asking Earth...</p>}

        {status === "error" && error && <p role="alert">Error: {error}</p>}

        {status === "success" && result && <EarthQueryResultView result={result} />}

        <ForecastPanel />
      </main>
    </>
  );
}
