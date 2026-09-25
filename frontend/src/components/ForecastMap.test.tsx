import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ForecastResult } from "../api/types";
import { ForecastMap } from "./ForecastMap";

function feature(
  tileId: string,
  latIndex: number,
  lonIndex: number,
  probability: number,
) {
  const minLon = -120 + lonIndex * 0.1;
  const minLat = 34 + latIndex * 0.1;

  return {
    type: "Feature" as const,
    id: tileId,
    geometry: { type: "Polygon" as const, coordinates: [] },
    properties: {
      tile_id: tileId,
      lat_index: latIndex,
      lon_index: lonIndex,
      min_lon: minLon,
      min_lat: minLat,
      max_lon: minLon + 0.1,
      max_lat: minLat + 0.1,
      centroid_lon: minLon + 0.05,
      centroid_lat: minLat + 0.05,
      probability,
    },
  };
}

function baseResult(overrides: Partial<ForecastResult> = {}): ForecastResult {
  return {
    grid: {
      type: "FeatureCollection",
      features: [
        feature("CA_0421_0583", 421, 583, 0.0374),
        feature("CA_0421_0584", 421, 584, 0.512),
        feature("CA_0422_0583", 422, 583, 0.021),
      ],
    },
    model_version: "v1",
    data_cutoff: "2024-08-21T00:00:00+00:00",
    forecast_window: {
      start: "2024-08-21T00:00:00+00:00",
      end: "2024-08-22T00:00:00+00:00",
      hours: 24,
    },
    calibration: {
      method: "isotonic",
      table: [
        { bin_index: 0, predicted_mean: 0.05, observed_frequency: 0.04, count: 120 },
        { bin_index: 1, predicted_mean: 0.5, observed_frequency: 0.48, count: 30 },
      ],
    },
    evidence: {
      dataset: "wildfire_forecast:v1",
      period_start: "2024-08-21T00:00:00+00:00",
      period_end: "2024-08-22T00:00:00+00:00",
      region_kind: "named",
      region_label: "california",
      region_bbox: [-124.5, 32.5, -114.0, 42.0],
      query_parameters: { cutoff: "2024-08-21T00:00:00+00:00", forecast_window_hours: 24 },
      processing_version: "0.1.0",
    },
    ...overrides,
  };
}

describe("ForecastMap", () => {
  it("renders one cell per grid feature, colored and labeled by its real probability", () => {
    render(<ForecastMap result={baseResult()} />);

    expect(screen.getByTestId("forecast-cell-CA_0421_0583")).toBeInTheDocument();
    expect(screen.getByTestId("forecast-cell-CA_0421_0584")).toBeInTheDocument();
    expect(screen.getByTestId("forecast-cell-CA_0422_0583")).toBeInTheDocument();

    expect(screen.getByTestId("forecast-cell-CA_0421_0584").querySelector("title")).toHaveTextContent(
      "51.2% risk",
    );
  });

  it("shows the model version, data cutoff and forecast window", () => {
    render(<ForecastMap result={baseResult()} />);

    const map = screen.getByLabelText("Forecast map");
    expect(map).toHaveTextContent("v1");
    expect(map).toHaveTextContent("2024-08-21T00:00:00+00:00");
    expect(map).toHaveTextContent("2024-08-22T00:00:00+00:00");
    expect(map).toHaveTextContent("24h");
  });

  it("shows a risk scale legend spanning the grid's real min and max probability", () => {
    render(<ForecastMap result={baseResult()} />);

    expect(
      screen.getByRole("img", { name: /risk color scale from 0.021 to 0.512/i }),
    ).toBeInTheDocument();
  });

  it("shows the calibration table", () => {
    render(<ForecastMap result={baseResult()} />);

    const details = screen.getByText("Calibration table").closest("details");
    expect(details).not.toBeNull();
    const table = within(details as HTMLElement);
    expect(table.getByText("0.05")).toBeInTheDocument();
    expect(table.getByText("120")).toBeInTheDocument();
  });

  it("shows a full table view of every grid cell, not just the map", () => {
    render(<ForecastMap result={baseResult()} />);

    const details = screen.getByText("Table view: all grid cells").closest("details");
    expect(details).not.toBeNull();
    expect(within(details as HTMLElement).getByText("CA_0421_0584")).toBeInTheDocument();
    expect(within(details as HTMLElement).getByText("0.512")).toBeInTheDocument();
  });

  it("explains what drove the forecast when the result carries SHAP values", () => {
    const riskiest = feature("CA_0421_0584", 421, 584, 0.512);
    riskiest.properties = {
      ...riskiest.properties,
      top_drivers: [
        { feature: "previous_7d_count", contribution: 2.31 },
        { feature: "relative_humidity", contribution: -0.4 },
      ],
    } as typeof riskiest.properties;
    render(
      <ForecastMap
        result={baseResult({
          grid: { type: "FeatureCollection", features: [riskiest] },
          explanation: {
            method: "xgboost_tree_shap",
            units: "log_odds",
            importance: [
              { feature: "previous_30d_count", contribution: 0.9126 },
              { feature: "elevation_m", contribution: 0.5963 },
            ],
          },
        })}
      />,
    );

    const drivers = screen.getByLabelText("What drove this forecast");
    expect(drivers).toHaveTextContent("Fires in the past 30 days");
    expect(drivers).toHaveTextContent("0.913");
    expect(drivers).toHaveTextContent("Fires in the past 7 days raises risk (2.31)");
    expect(drivers).toHaveTextContent("Relative humidity lowers risk (-0.40)");
    expect(screen.getByTestId("forecast-cell-CA_0421_0584").querySelector("title")).toHaveTextContent(
      "Fires in the past 7 days raises risk",
    );
  });

  it("omits the drivers section when the result has no explanation", () => {
    render(<ForecastMap result={baseResult()} />);

    expect(screen.queryByLabelText("What drove this forecast")).toBeNull();
  });

  it("shows the forecast's own evidence", () => {
    render(<ForecastMap result={baseResult()} />);

    const map = screen.getByLabelText("Forecast map");
    expect(map).toHaveTextContent("wildfire_forecast:v1");
    expect(map).toHaveTextContent("named (california)");
  });
});
