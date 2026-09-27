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

export interface ForecastRequest {
  region: RegionSpec;
  cutoff: string;
}

export interface ForecastSummary {
  forecast_id: string;
  status: string;
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

export interface EarthQueryRequest {
  question: string;
}

export interface EarthQuerySummary {
  id: string;
  status: "SUCCEEDED" | "FAILED";
}

export interface DatasetReference {
  source: string;
  product: string;
  record_count: number;
  provenance: Record<string, unknown>;
}

export interface ForecastJobReference {
  forecast_id: string;
  status: string;
}

export type EarthQueryFactResult =
  | CountResult
  | DailyAggregateResult
  | WeeklyAggregateResult
  | MapResult
  | DatasetReference
  | ForecastResultSummary
  | DocsSearchResult
  | ForecastJobReference;

export interface DocsPassage {
  source: string;
  heading: string;
  text: string;
  score: number;
}

export interface DocsSearchResult {
  query: string;
  retrieval?: string;
  passages: DocsPassage[];
}

export interface ForecastSummaryCell {
  tile_id: string;
  centroid_lat: number;
  centroid_lon: number;
  probability: number;
  top_drivers: FeatureContribution[];
}

export interface ForecastResultSummary {
  forecast_id: string;
  model_version: string;
  data_cutoff: string;
  forecast_window: { start: string; end: string; hours: number };
  cell_count: number;
  max_probability: number | null;
  mean_probability: number | null;
  top_cells: ForecastSummaryCell[];
  drivers: FeatureContribution[];
  explanation_units: string | null;
}

export interface GroundingCheck {
  verified: boolean;
  checked: number;
  unsupported: string[];
  unknown_tags: string[];
  unknown_citations?: string[];
}

export interface EarthQueryFact {
  step_id: string;
  category: "observed" | "computed" | "predicted" | "documented";
  result: EarthQueryFactResult;
  evidence: Evidence | null;
}

export interface EarthQueryPlanStep {
  step_id: string;
  tool: string;
  input: Record<string, unknown>;
  depends_on: string[];
}

export interface EarthQueryResult {
  question: string;
  answer: string;
  grounding?: GroundingCheck | null;
  facts: EarthQueryFact[];
  outputs: Record<string, unknown>;
  plan: { steps: EarthQueryPlanStep[] };
}

export interface EarthQueryResultResponse {
  id: string;
  result: EarthQueryResult;
}

export interface ForecastGridFeature {
  type: "Feature";
  id: string;
  geometry: { type: "Polygon"; coordinates: number[][][] };
  properties: {
    tile_id: string;
    lat_index: number;
    lon_index: number;
    min_lon: number;
    min_lat: number;
    max_lon: number;
    max_lat: number;
    centroid_lon: number;
    centroid_lat: number;
    probability: number;
    top_drivers?: FeatureContribution[];
  };
}

export interface FeatureContribution {
  feature: string;
  contribution: number;
}

export interface ForecastExplanation {
  method: string;
  units: string;
  importance: FeatureContribution[];
}

export interface ForecastGrid {
  type: "FeatureCollection";
  features: ForecastGridFeature[];
}

export interface ForecastWindow {
  start: string;
  end: string;
  hours: number;
}

export interface CalibrationBin {
  bin_index: number;
  predicted_mean: number;
  observed_frequency: number;
  count: number;
}

export interface CalibrationMetadata {
  method: string;
  table: CalibrationBin[];
}

export interface ForecastResult {
  grid: ForecastGrid;
  model_version: string;
  data_cutoff: string;
  forecast_window: ForecastWindow;
  calibration: CalibrationMetadata;
  evidence: Evidence;
  explanation?: ForecastExplanation;
}

export interface ForecastResultResponse {
  forecast_id: string;
  result: ForecastResult;
}
