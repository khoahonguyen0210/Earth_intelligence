import { useEffect, useState } from "react";
import { createForecast, getForecastResult, getForecastStatus } from "../api/client";
import type { ForecastRequest, ForecastResult } from "../api/types";
import { ForecastMap } from "./ForecastMap";
import { ForecastRequestForm } from "./ForecastRequestForm";

const DEFAULT_POLL_INTERVAL_MS = 2000;

type DisplayStatus = "queued" | "running" | "completed" | "failed";

function toDisplayStatus(backendStatus: string): DisplayStatus {
  switch (backendStatus) {
    case "PENDING":
    case "RETRYING":
      return "queued";
    case "RUNNING":
      return "running";
    case "SUCCEEDED":
      return "completed";
    default:
      return "failed";
  }
}

function isTerminalStatus(backendStatus: string): boolean {
  return backendStatus === "SUCCEEDED" || backendStatus === "FAILED" || backendStatus === "CANCELLED";
}

const STATUS_BADGE: Record<DisplayStatus, { glyph: string; color: string; label: string }> = {
  queued: { glyph: "…", color: "#ec835a", label: "Queued" },
  running: { glyph: "▶", color: "#fab219", label: "Running" },
  completed: { glyph: "✓", color: "#0ca30c", label: "Completed" },
  failed: { glyph: "✕", color: "#d03b3b", label: "Failed" },
};

function StatusBadge({ backendStatus }: { backendStatus: string }) {
  const displayStatus = toDisplayStatus(backendStatus);
  const badge = STATUS_BADGE[displayStatus];

  return (
    <p
      role="status"
      aria-label="Forecast job status"
      className={`status-badge status-${displayStatus}`}
    >
      <svg width={16} height={16} aria-hidden="true">
        <text x={8} y={12} textAnchor="middle" fontSize={13} fill={badge.color}>
          {badge.glyph}
        </text>
      </svg>{" "}
      <strong>{badge.label}</strong> ({backendStatus})
    </p>
  );
}

interface ForecastPanelProps {
  pollIntervalMs?: number;
}

export function ForecastPanel({ pollIntervalMs = DEFAULT_POLL_INTERVAL_MS }: ForecastPanelProps) {
  const [forecastId, setForecastId] = useState<string | null>(null);
  const [backendStatus, setBackendStatus] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [result, setResult] = useState<ForecastResult | null>(null);
  const [resultError, setResultError] = useState<string | null>(null);

  async function handleSubmit(request: ForecastRequest) {
    setSubmitError(null);
    setResult(null);
    setResultError(null);
    setForecastId(null);
    setBackendStatus(null);

    try {
      const summary = await createForecast(request);
      setForecastId(summary.forecast_id);
      setBackendStatus(summary.status);
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "Unknown error");
    }
  }

  useEffect(() => {
    if (!forecastId || !backendStatus || isTerminalStatus(backendStatus)) {
      return;
    }

    const timer = setInterval(() => {
      getForecastStatus(forecastId)
        .then((summary) => setBackendStatus(summary.status))
        .catch((err) => setSubmitError(err instanceof Error ? err.message : "Unknown error"));
    }, pollIntervalMs);

    return () => clearInterval(timer);
  }, [forecastId, backendStatus, pollIntervalMs]);

  useEffect(() => {
    if (!forecastId || (backendStatus !== "SUCCEEDED" && backendStatus !== "FAILED")) {
      return;
    }

    let ignore = false;
    getForecastResult(forecastId)
      .then((response) => {
        if (!ignore) {
          setResult(response.result);
        }
      })
      .catch((err) => {
        if (!ignore) {
          setResultError(err instanceof Error ? err.message : "Unknown error");
        }
      });

    return () => {
      ignore = true;
    };
  }, [forecastId, backendStatus]);

  return (
    <section aria-label="Forecast">
      <h2>Forecast</h2>
      <ForecastRequestForm
        onSubmit={handleSubmit}
        disabled={Boolean(backendStatus && !isTerminalStatus(backendStatus))}
      />

      {submitError && <p role="alert">Error: {submitError}</p>}

      {backendStatus && <StatusBadge backendStatus={backendStatus} />}

      {backendStatus === "FAILED" && resultError && <p role="alert">Error: {resultError}</p>}

      {backendStatus === "SUCCEEDED" && result && <ForecastMap result={result} />}
    </section>
  );
}
