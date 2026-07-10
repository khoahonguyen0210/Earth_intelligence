import type {
  AnalysisRequest,
  AnalysisSummary,
  ErrorResponse,
  ResultResponse,
} from "./types";

const API_BASE_URL = "http://localhost:8080";

export async function getHealth() {
  const response = await fetch(`${API_BASE_URL}/actuator/health`);

  if (!response.ok) {
    throw new Error(`API request failed: ${response.status}`);
  }

  return response.json();
}

export async function createAnalysis(
  request: AnalysisRequest,
): Promise<AnalysisSummary> {
  const response = await fetch(`${API_BASE_URL}/analyses`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    throw new Error(`Failed to create analysis: ${response.status}`);
  }

  return response.json();
}

export async function getAnalysisResult(
  id: string,
): Promise<ResultResponse> {
  const response = await fetch(`${API_BASE_URL}/results/${id}`);
  const body = await response.json();

  if (!response.ok) {
    const errorBody = body as ErrorResponse;
    throw new Error(errorBody.error ?? `Failed to fetch result: ${response.status}`);
  }

  return body as ResultResponse;
}
