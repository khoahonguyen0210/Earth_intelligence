import { useEffect, useState } from "react";
import { createAnalysis, getAnalysisResult, getHealth } from "./api/client";
import type { AnalysisRequest, ResultResponse } from "./api/types";
import { QueryForm } from "./components/QueryForm";
import { ResultView } from "./components/ResultView";

type Status = "idle" | "loading" | "error" | "success";

function App() {
  const [backendStatus, setBackendStatus] = useState("Checking backend...");
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ResultResponse | null>(null);
  const [submittedQuestion, setSubmittedQuestion] = useState<string | null>(
    null,
  );

  useEffect(() => {
    getHealth()
      .then((data) => setBackendStatus(`Backend: ${data.status}`))
      .catch(() => setBackendStatus("Backend: unavailable"));
  }, []);

  async function handleSubmit(request: AnalysisRequest) {
    setStatus("loading");
    setError(null);
    setResult(null);
    setSubmittedQuestion(request.question);

    try {
      const summary = await createAnalysis(request);
      const resultResponse = await getAnalysisResult(summary.id);
      setResult(resultResponse);
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

      <QueryForm onSubmit={handleSubmit} disabled={status === "loading"} />

      {status === "loading" && <p role="status">Running analysis...</p>}

      {status === "error" && error && <p role="alert">Error: {error}</p>}

      {status === "success" && result && (
        <>
          <p>
            <em>{submittedQuestion}</em>
          </p>
          <ResultView result={result.result} evidence={result.evidence} />
        </>
      )}
    </main>
  );
}

export default App;
