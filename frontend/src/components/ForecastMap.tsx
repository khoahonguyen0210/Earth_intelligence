import type { CalibrationBin, ForecastGridFeature, ForecastResult } from "../api/types";

// Same California reference frame RegionMap draws against, so a forecast
// grid (docs/forecast-api-contract.md's CALIFORNIA_BBOX) reads at the same
// scale as the region maps elsewhere on the page.
const REFERENCE_BBOX: [number, number, number, number] = [
  -124.5, 32.5, -114.0, 42.0,
];

const VIEW_SIZE = 320;
const PADDING = 12;

// Sequential "blue" ramp, steps 100/200/300/400/500/600/700 from the
// dataviz skill's validated reference palette -- a magnitude encoding
// (probability), never identity, so no CVD re-validation is needed: this
// is the unmodified reference instance.
const RISK_RAMP = [
  "#cde2fb",
  "#9ec5f4",
  "#6da7ec",
  "#3987e5",
  "#256abf",
  "#184f95",
  "#0d366b",
];

function colorForProbability(value: number, min: number, max: number): string {
  if (max <= min) {
    return RISK_RAMP[Math.floor(RISK_RAMP.length / 2)];
  }

  const t = (value - min) / (max - min);
  const index = Math.min(
    RISK_RAMP.length - 1,
    Math.max(0, Math.round(t * (RISK_RAMP.length - 1))),
  );
  return RISK_RAMP[index];
}

interface ForecastMapProps {
  result: ForecastResult;
}

function RiskLegend({ min, max }: { min: number; max: number }) {
  const swatchWidth = 28;
  const swatchHeight = 14;

  return (
    <figure aria-label="Risk scale legend">
      <svg
        role="img"
        aria-label={`Risk color scale from ${min.toFixed(3)} to ${max.toFixed(3)} probability`}
        width={swatchWidth * RISK_RAMP.length}
        height={swatchHeight}
      >
        {RISK_RAMP.map((hex, index) => (
          <rect
            key={hex}
            x={index * swatchWidth}
            y={0}
            width={swatchWidth - 1}
            height={swatchHeight}
            fill={hex}
          />
        ))}
      </svg>
      <figcaption>
        {min.toFixed(3)} (lowest risk) &ndash; {max.toFixed(3)} (highest risk)
      </figcaption>
    </figure>
  );
}

/**
 * The forecast map: California grid, risk value, legend, forecast
 * horizon, data cutoff, model, calibration/evidence -- rendered only
 * from the real GET /forecasts/{id}/result shape
 * (forecast_result_to_dict), nothing fabricated. A job's own status
 * polling (queued/running/failed) and wiring this into the result page
 * happen elsewhere; this component only ever receives an already
 * SUCCEEDED forecast's result.
 */
export function ForecastMap({ result }: ForecastMapProps) {
  const { grid, model_version, data_cutoff, forecast_window, calibration, evidence } = result;
  const [refWest, refSouth, refEast, refNorth] = REFERENCE_BBOX;

  const plotSize = VIEW_SIZE - PADDING * 2;
  const scaleX = plotSize / (refEast - refWest);
  const scaleY = plotSize / (refNorth - refSouth);

  function project(lon: number, lat: number): [number, number] {
    const x = PADDING + (lon - refWest) * scaleX;
    const y = PADDING + (refNorth - lat) * scaleY; // SVG y grows downward
    return [x, y];
  }

  const probabilities = grid.features.map((feature) => feature.properties.probability);
  const minProbability = probabilities.length > 0 ? Math.min(...probabilities) : 0;
  const maxProbability = probabilities.length > 0 ? Math.max(...probabilities) : 0;

  const cellsByRisk = [...grid.features].sort(
    (a, b) => b.properties.probability - a.properties.probability,
  );

  return (
    <section aria-label="Forecast map">
      <h3>Wildfire risk forecast</h3>

      <svg
        role="img"
        aria-label={`Forecast risk grid, model ${model_version}`}
        width={VIEW_SIZE}
        height={VIEW_SIZE}
        viewBox={`0 0 ${VIEW_SIZE} ${VIEW_SIZE}`}
      >
        <rect
          x={PADDING}
          y={PADDING}
          width={plotSize}
          height={plotSize}
          fill="#fcfcfb"
          stroke="#c3c2b7"
        />

        {grid.features.map((feature: ForecastGridFeature) => {
          const { tile_id, min_lon, min_lat, max_lon, max_lat, probability } = feature.properties;
          const [x0, y0] = project(min_lon, max_lat);
          const [x1, y1] = project(max_lon, min_lat);

          return (
            <rect
              key={tile_id}
              data-testid={`forecast-cell-${tile_id}`}
              x={Math.min(x0, x1)}
              y={Math.min(y0, y1)}
              width={Math.max(Math.abs(x1 - x0) - 1, 1)}
              height={Math.max(Math.abs(y1 - y0) - 1, 1)}
              fill={colorForProbability(probability, minProbability, maxProbability)}
            >
              <title>{`${tile_id}: ${(probability * 100).toFixed(1)}% risk`}</title>
            </rect>
          );
        })}
      </svg>

      <RiskLegend min={minProbability} max={maxProbability} />

      <dl>
        <dt>Model</dt>
        <dd>{model_version}</dd>
        <dt>Data cutoff</dt>
        <dd>{data_cutoff}</dd>
        <dt>Forecast window</dt>
        <dd>
          {forecast_window.start} &ndash; {forecast_window.end} ({forecast_window.hours}h)
        </dd>
        <dt>Calibration method</dt>
        <dd>{calibration.method}</dd>
      </dl>

      {calibration.table.length > 0 && (
        <details>
          <summary>Calibration table</summary>
          <table>
            <caption>Calibration bins: predicted vs. observed frequency</caption>
            <thead>
              <tr>
                <th>Bin</th>
                <th>Predicted mean</th>
                <th>Observed frequency</th>
                <th>Count</th>
              </tr>
            </thead>
            <tbody>
              {calibration.table.map((bin: CalibrationBin) => (
                <tr key={bin.bin_index}>
                  <td>{bin.bin_index}</td>
                  <td>{bin.predicted_mean}</td>
                  <td>{bin.observed_frequency}</td>
                  <td>{bin.count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      )}

      <details>
        <summary>Table view: all grid cells</summary>
        <table>
          <caption>Forecast grid cells, highest risk first</caption>
          <thead>
            <tr>
              <th>Tile</th>
              <th>Centroid (lat, lon)</th>
              <th>Probability</th>
            </tr>
          </thead>
          <tbody>
            {cellsByRisk.map((feature) => (
              <tr key={feature.properties.tile_id}>
                <td>{feature.properties.tile_id}</td>
                <td>
                  {feature.properties.centroid_lat}, {feature.properties.centroid_lon}
                </td>
                <td>{feature.properties.probability}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>

      <h4>Evidence</h4>
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
