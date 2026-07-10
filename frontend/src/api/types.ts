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
