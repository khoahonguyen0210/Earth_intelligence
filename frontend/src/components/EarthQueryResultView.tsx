import type {
  CountResult,
  DailyAggregateResult,
  DatasetReference,
  EarthQueryFact,
  EarthQueryFactResult,
  EarthQueryResult,
  ForecastJobReference,
  ForecastResultSummary,
  GroundingCheck,
  MapResult,
  WeeklyAggregateResult,
} from "../api/types";
import { featureLabel } from "./featureLabels";
import { RegionMap } from "./RegionMap";

interface EarthQueryResultViewProps {
  result: EarthQueryResult;
}

function isCountResult(result: EarthQueryFactResult): result is CountResult {
  return typeof (result as CountResult).count === "number";
}

function isDailyAggregateResult(
  result: EarthQueryFactResult,
): result is DailyAggregateResult {
  return Array.isArray((result as DailyAggregateResult).daily);
}

function isWeeklyAggregateResult(
  result: EarthQueryFactResult,
): result is WeeklyAggregateResult {
  return Array.isArray((result as WeeklyAggregateResult).weekly);
}

function isMapResult(result: EarthQueryFactResult): result is MapResult {
  return (result as MapResult).type === "FeatureCollection";
}

function isDatasetReference(
  result: EarthQueryFactResult,
): result is DatasetReference {
  return typeof (result as DatasetReference).record_count === "number";
}

function isForecastSummary(result: EarthQueryFactResult): result is ForecastResultSummary {
  return Array.isArray((result as ForecastResultSummary).top_cells);
}

function isForecastJobReference(
  result: EarthQueryFactResult,
): result is ForecastJobReference {
  return typeof (result as ForecastJobReference).forecast_id === "string";
}

function FactBody({ result }: { result: EarthQueryFactResult }) {
  if (isCountResult(result)) {
    return (
      <p data-testid={`result-count`}>
        <strong>{result.count}</strong> fire detections
      </p>
    );
  }

  if (isDailyAggregateResult(result)) {
    return (
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
    );
  }

  if (isWeeklyAggregateResult(result)) {
    return (
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
    );
  }

  if (isMapResult(result)) {
    return (
      <ul aria-label="Map values">
        {result.features.map((feature, index) => (
          <li key={index}>
            {feature.properties.region_label ?? feature.properties.region_kind}:{" "}
            {feature.properties.value} {feature.properties.units}
          </li>
        ))}
      </ul>
    );
  }

  if (isForecastSummary(result)) {
    return (
      <div data-testid="result-forecast-summary">
        <p>
          Highest risk{" "}
          <strong>
            {result.max_probability === null
              ? "n/a"
              : `${(result.max_probability * 100).toFixed(1)}%`}
          </strong>{" "}
          across {result.cell_count} grid cells.
        </p>
        {result.drivers.length > 0 && (
          <p>
            Main drivers:{" "}
            {result.drivers
              .slice(0, 3)
              .map((driver) => featureLabel(driver.feature))
              .join(", ")}
            .
          </p>
        )}
      </div>
    );
  }

  if (isForecastJobReference(result)) {
    return (
      <p>
        Forecast job <code>{result.forecast_id}</code>: {result.status}. Its
        risk grid is shown on the forecast map.
      </p>
    );
  }

  if (isDatasetReference(result)) {
    return (
      <p>
        <strong>{result.record_count}</strong> records from {result.source} (
        {result.product})
      </p>
    );
  }

  return null;
}

function Fact({ fact }: { fact: EarthQueryFact }) {
  const { evidence } = fact;

  return (
    <article aria-label={`Step ${fact.step_id}`}>
      <h3>
        {fact.step_id} <em>({fact.category})</em>
      </h3>

      <FactBody result={fact.result} />

      {evidence && (
        <>
          <h4>Region</h4>
          <RegionMap bbox={evidence.region_bbox} label={evidence.region_label} />
          <p>
            {evidence.region_kind}
            {evidence.region_label ? ` (${evidence.region_label})` : ""}
          </p>

          <h4>Time</h4>
          <p>
            {evidence.period_start} to {evidence.period_end}
          </p>

          <h4>Evidence</h4>
          <dl>
            <dt>Dataset</dt>
            <dd>{evidence.dataset}</dd>
            <dt>Processing version</dt>
            <dd>{evidence.processing_version}</dd>
          </dl>
        </>
      )}
    </article>
  );
}

function GroundingBadge({ grounding }: { grounding: GroundingCheck }) {
  if (grounding.verified) {
    return (
      <p className="grounding grounding-ok" data-testid="grounding">
        {grounding.checked > 0
          ? `All ${grounding.checked} numbers in this answer match the computed results.`
          : "This answer states no numbers."}
      </p>
    );
  }

  const problems = [
    ...grounding.unsupported.map((value) => `"${value}" is not in the results`),
    ...grounding.unknown_tags.map((tag) => `tag "${tag}" matches no result`),
  ];
  return (
    <p className="grounding grounding-warn" role="alert" data-testid="grounding">
      Check this answer: {problems.join("; ")}.
    </p>
  );
}

export function EarthQueryResultView({ result }: EarthQueryResultViewProps) {
  return (
    <section aria-label="Answer" data-testid="ask-earth-answer">
      <h2>Answer</h2>
      <p>{result.answer}</p>
      {result.grounding && <GroundingBadge grounding={result.grounding} />}

      {result.facts.length > 0 && (
        <div aria-label="Facts behind this answer">
          {result.facts.map((fact) => (
            <Fact key={fact.step_id} fact={fact} />
          ))}
        </div>
      )}
    </section>
  );
}
