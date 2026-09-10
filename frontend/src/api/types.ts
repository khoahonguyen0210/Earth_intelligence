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

// Task 14.4: a direct forecast job request (docs/forecast-api-contract.md's
// POST /forecasts), independent of Ask Earth's own embedded run_forecast
// step -- this is the real async job path (queued/running/completed/failed),
// not the synchronous /queries flow.
export interface ForecastRequest {
  region: RegionSpec;
  cutoff: string;
}

/** The backend's real, unmapped status (Forecast.Status): PENDING, RUNNING,
 * SUCCEEDED, FAILED, RETRYING, or CANCELLED (the last unreachable today --
 * no cancel endpoint exists). `forecast_id`, not `forecastId`: Jackson
 * serializes every backend response as snake_case
 * (spring.jackson.property-naming-strategy=SNAKE_CASE), confirmed against
 * the real running backend, not assumed from the Java record's own field
 * name. */
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

/** get_data's own output shape (docs/ask-earth.md): a dataset reference, never raw records. */
export interface DatasetReference {
  source: string;
  product: string;
  record_count: number;
  provenance: Record<string, unknown>;
}

/** run_forecast's own output shape: it only creates the job (docs/forecast-api-contract.md); Task 14.3 renders the real grid. */
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
  | ForecastJobReference;

export interface EarthQueryFact {
  step_id: string;
  category: "observed" | "computed" | "predicted";
  result: EarthQueryFactResult;
  // Only calculate_statistics/generate_map carry their own Evidence
  // (query.run_analysis); get_data/run_forecast facts have none of their
  // own -- a forecast's evidence comes from a separate
  // get_result_evidence step in the same plan, not inline.
  evidence: Evidence | null;
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

// Task 14.3: the real forecast result shape (docs/forecast-api-contract.md,
// ml/src/.../query/forecast_result.py's forecast_result_to_dict). A
// run_forecast fact only ever carries a job reference (ForecastJobReference
// above); once that job is SUCCEEDED, GET /forecasts/{id}/result serves this.

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
  };
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
}

export interface ForecastResultResponse {
  forecast_id: string;
  result: ForecastResult;
}
