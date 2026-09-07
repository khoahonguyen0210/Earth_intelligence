export type RegionKind = "bbox" | "coordinates" | "named";

export type RegionValue =
  | string
  | [number, number]
  | [number, number, number, number];

export interface RegionSpec {
  kind: RegionKind;
  value: RegionValue;
}

export interface TimeRangeSpec {
  start: string;
  end: string;
}

export type Operation = "count" | "daily_aggregate" | "weekly_aggregate" | "map";
export type Intent = "count" | "aggregate" | "compare" | "trend" | "map" | "forecast";

export interface AnalysisRequest {
  question: string;
  intent: Intent;
  region: RegionSpec;
  time_range: TimeRangeSpec;
  operation: Operation;
}

export interface AnalysisSummary {
  id: string;
  status: "SUCCEEDED" | "FAILED";
}

export interface Evidence {
  dataset: string;
  period_start: string;
  period_end: string;
  region_kind: string;
  region_label: string | null;
  region_bbox: [number, number, number, number];
  query_parameters: Record<string, unknown>;
  processing_version: string;
}

export interface CountResult {
  count: number;
}

export interface DailyAggregateResult {
  daily: { date: string; count: number }[];
}

export interface WeeklyAggregateResult {
  weekly: { week_start: string; count: number }[];
}

export interface MapFeature {
  type: "Feature";
  geometry: { type: "Polygon"; coordinates: number[][][] };
  properties: {
    value: number;
    time: { start: string; end: string };
    units: string;
    region_kind: string;
    region_label: string | null;
  };
}

export interface MapResult {
  type: "FeatureCollection";
  features: MapFeature[];
}

export type AnalysisResult =
  | CountResult
  | DailyAggregateResult
  | WeeklyAggregateResult
  | MapResult;

export interface ResultResponse {
  id: string;
  result: AnalysisResult;
  evidence: Evidence;
}

export interface ErrorResponse {
  error: string;
}

// Task 14.1: the Ask Earth page's own types -- POST /queries takes a
// bare natural-language question; everything else (region, time range,
// operation) is what the real planner (backend, Task 7.3) works out,
// not something this page's request shape carries.

export interface EarthQueryRequest {
  question: string;
}

export interface EarthQuerySummary {
  id: string;
  status: "SUCCEEDED" | "FAILED";
}

export interface EarthQueryFact {
  step_id: string;
  category: "observed" | "computed" | "predicted";
  result: unknown;
  evidence: Record<string, unknown> | null;
}

export interface EarthQueryPlanStep {
  step_id: string;
  tool: string;
  input: Record<string, unknown>;
  depends_on: string[];
}

/**
 * The whole run_ask_earth.py payload (docs/ask-earth.md): a grounded
 * answer plus the real facts, outputs and plan behind it. Task 14.2's
 * result page is what actually renders outputs/plan (map, numbers,
 * evidence); this page only needs `answer`.
 */
export interface EarthQueryResult {
  question: string;
  answer: string;
  facts: EarthQueryFact[];
  outputs: Record<string, unknown>;
  plan: { steps: EarthQueryPlanStep[] };
}

export interface EarthQueryResultResponse {
  id: string;
  result: EarthQueryResult;
}
