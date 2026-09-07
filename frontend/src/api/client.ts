import type {
  AnalysisRequest,
  AnalysisSummary,
  EarthQueryResultResponse,
  EarthQuerySummary,
  ErrorResponse,
  ResultResponse,
} from "./types";

const API_BASE_URL = "http://localhost:8080";

export async function getHealth() {
  const response = await fetch(`${API_BASE_URL}/readyz`);

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

// Task 14.1: the Ask Earth page's own calls -- POST /queries is
// synchronous (no job queue, like /analyses), so a caller awaits it and
// then fetches the result in sequence, exactly like
// createAnalysis/getAnalysisResult above.

export async function createEarthQuery(question: string): Promise<EarthQuerySummary> {
  const response = await fetch(`${API_BASE_URL}/queries`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
  const body = await response.json();

  if (!response.ok) {
    const errorBody = body as ErrorResponse;
    throw new Error(errorBody.error ?? `Failed to create query: ${response.status}`);
  }

  return body as EarthQuerySummary;
}

export async function getEarthQueryResult(id: string): Promise<EarthQueryResultResponse> {
  const response = await fetch(`${API_BASE_URL}/queries/${id}/result`);
  const body = await response.json();

  if (!response.ok) {
    const errorBody = body as ErrorResponse;
    throw new Error(errorBody.error ?? `Failed to fetch query result: ${response.status}`);
  }

  return body as EarthQueryResultResponse;
}
