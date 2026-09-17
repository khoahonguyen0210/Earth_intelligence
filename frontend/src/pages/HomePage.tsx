import { useState } from "react";
import { Link } from "react-router-dom";
import { createEarthQuery, getEarthQueryResult } from "../api/client";
import type { EarthQueryResult } from "../api/types";
import { AskEarthForm } from "../components/AskEarthForm";
import { EarthQueryResultView } from "../components/EarthQueryResultView";
import { EmberField } from "../components/EmberField";
import { ForecastPanel } from "../components/ForecastPanel";
import { useCountUp } from "../hooks/useCountUp";

type Status = "idle" | "loading" | "error" | "success";

const STATS = [
  { value: "0.45", label: "PR-AUC on real 2024 test data" },
  { value: "100%", label: "planner execution success, live API" },
  { value: "1.35s", label: "recovery from a real killed worker" },
  { value: "4", label: "real Earth-observation data sources" },
];

const FEATURES = [
  {
    title: "Ask in plain English",
    body: "A real LLM turns your question into a structured plan. A deterministic validator checks that plan before anything runs, so the model can never bypass the gate or run arbitrary code.",
  },
  {
    title: "24-hour wildfire risk",
    body: "A calibrated XGBoost model trained on real California fire history, weather, and terrain from 2019 to 2022. Not a guess, and not a black box: every prediction ships with its own calibration table.",
  },
  {
    title: "Every answer has evidence",
    body: "Dataset, region, time period, model version, and calibration are attached to every single result, always, so you can trace any number back to exactly what produced it.",
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
        <span className="kicker">Earth Intelligence &amp; Wildfire Forecasting</span>
        <h1>Ask Earth a question. Get a real, evidence-backed answer.</h1>
        <p className="hero-sub">
          Ask in plain English and get an answer built from real NASA and Copernicus
          data, a validated AI workflow, and a trained forecasting model, with every
          number traceable to what actually produced it, never fabricated.
        </p>
        <div className="hero-cta">
          <a href="#ask-earth" className="btn-primary">
            Ask Earth a question
          </a>
          <Link to="/results" className="btn-secondary">
            See real results &rarr;
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
