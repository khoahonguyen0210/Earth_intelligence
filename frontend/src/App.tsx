import { useEffect, useState } from "react";
import { createEarthQuery, getEarthQueryResult, getHealth } from "./api/client";
import type { EarthQueryResult } from "./api/types";
import { AskEarthForm } from "./components/AskEarthForm";
import { EarthQueryResultView } from "./components/EarthQueryResultView";
import { ForecastPanel } from "./components/ForecastPanel";

type Status = "idle" | "loading" | "error" | "success";

function App() {
  const [backendStatus, setBackendStatus] = useState("Checking backend...");
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<EarthQueryResult | null>(null);

  useEffect(() => {
    getHealth()
      .then((data) => setBackendStatus(`Backend: ${data.status}`))
      .catch(() => setBackendStatus("Backend: unavailable"));
  }, []);

  // Task 14.1: POST /queries is synchronous (no job queue, like
  // /analyses), so this awaits the real plan-and-execute pipeline
  // directly rather than polling a status.
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
    <main>
      <h1>AI Earth Intelligence & Forecasting Engine</h1>
      <p>{backendStatus}</p>

      <AskEarthForm onSubmit={handleAsk} disabled={status === "loading"} />

      {status === "loading" && <p role="status">Asking Earth...</p>}

      {status === "error" && error && <p role="alert">Error: {error}</p>}

      {status === "success" && result && <EarthQueryResultView result={result} />}

      <ForecastPanel />
    </main>
  );
}

export default App;
