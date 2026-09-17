import type {
  AnalysisRequest,
  AnalysisSummary,
  EarthQueryResultResponse,
  EarthQuerySummary,
  ErrorResponse,
  ForecastRequest,
  ForecastResultResponse,
  ForecastSummary,
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

export async function getForecastResult(id: string): Promise<ForecastResultResponse> {
  const response = await fetch(`${API_BASE_URL}/forecasts/${id}/result`);
  const body = await response.json();

  if (!response.ok) {
    const errorBody = body as ErrorResponse;
    throw new Error(errorBody.error ?? `Failed to fetch forecast result: ${response.status}`);
  }

  return body as ForecastResultResponse;
}

export async function createForecast(request: ForecastRequest): Promise<ForecastSummary> {
  const response = await fetch(`${API_BASE_URL}/forecasts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  const body = await response.json();

  if (!response.ok) {
    const errorBody = body as ErrorResponse;
    throw new Error(errorBody.error ?? `Failed to create forecast: ${response.status}`);
  }

  return body as ForecastSummary;
}

export async function getForecastStatus(id: string): Promise<ForecastSummary> {
  const response = await fetch(`${API_BASE_URL}/forecasts/${id}`);

  if (!response.ok) {
    throw new Error(`Failed to fetch forecast status: ${response.status}`);
  }

  return (await response.json()) as ForecastSummary;
}
