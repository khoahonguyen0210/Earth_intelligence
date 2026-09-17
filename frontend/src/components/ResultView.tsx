import type {
  AnalysisResult,
  CountResult,
  DailyAggregateResult,
  Evidence,
  MapResult,
  WeeklyAggregateResult,
} from "../api/types";
import { RegionMap } from "./RegionMap";

interface ResultViewProps {
  result: AnalysisResult;
  evidence: Evidence;
}

function isCountResult(result: AnalysisResult): result is CountResult {
  return typeof (result as CountResult).count === "number";
}

function isDailyAggregateResult(
  result: AnalysisResult,
): result is DailyAggregateResult {
  return Array.isArray((result as DailyAggregateResult).daily);
}

function isWeeklyAggregateResult(
  result: AnalysisResult,
): result is WeeklyAggregateResult {
  return Array.isArray((result as WeeklyAggregateResult).weekly);
}

function isMapResult(result: AnalysisResult): result is MapResult {
  return (result as MapResult).type === "FeatureCollection";
}

export function ResultView({ result, evidence }: ResultViewProps) {
  return (
    <section aria-label="Analysis result">
      <h2>Result</h2>

      {isCountResult(result) && (
        <p data-testid="result-count">
          <strong>{result.count}</strong> fire detections
        </p>
      )}

      {isDailyAggregateResult(result) && (
        <table>
          <caption>Daily fire counts</caption>
          <thead>
            <tr>
              <th>Date</th>
              <th>Count</th>
            </tr>
          </thead>
          <tbody>
            {result.daily.map((entry) => (
              <tr key={entry.date}>
                <td>{entry.date}</td>
                <td>{entry.count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {isWeeklyAggregateResult(result) && (
        <table>
          <caption>Weekly fire counts</caption>
          <thead>
            <tr>
              <th>Week starting</th>
              <th>Count</th>
            </tr>
          </thead>
          <tbody>
            {result.weekly.map((entry) => (
              <tr key={entry.week_start}>
                <td>{entry.week_start}</td>
                <td>{entry.count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {isMapResult(result) && (
        <ul>
          {result.features.map((feature, index) => (
            <li key={index}>
              {feature.properties.region_label ?? feature.properties.region_kind}:{" "}
              {feature.properties.value} {feature.properties.units}
            </li>
          ))}
        </ul>
      )}

      <h3>Region map</h3>
      <RegionMap bbox={evidence.region_bbox} label={evidence.region_label} />

      <h3>Time range</h3>
      <p>
        {evidence.period_start} to {evidence.period_end}
      </p>

      <h3>Evidence</h3>
      <dl>
        <dt>Dataset</dt>
        <dd>{evidence.dataset}</dd>
        <dt>Region</dt>
        <dd>
          {evidence.region_kind}
          {evidence.region_label ? ` (${evidence.region_label})` : ""}
        </dd>
        <dt>Processing version</dt>
        <dd>{evidence.processing_version}</dd>
      </dl>
    </section>
  );
}
