import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ForecastResult } from "../api/types";
import { ForecastPanel } from "./ForecastPanel";

const mockCreateForecast = vi.fn();
const mockGetForecastStatus = vi.fn();
const mockGetForecastResult = vi.fn();

vi.mock("../api/client", () => ({
  createForecast: (...args: unknown[]) => mockCreateForecast(...args),
  getForecastStatus: (...args: unknown[]) => mockGetForecastStatus(...args),
  getForecastResult: (...args: unknown[]) => mockGetForecastResult(...args),
}));

const RESULT: ForecastResult = {
  grid: {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        id: "CA_0421_0583",
        geometry: { type: "Polygon", coordinates: [] },
        properties: {
          tile_id: "CA_0421_0583",
          lat_index: 421,
          lon_index: 583,
          min_lon: -120,
          min_lat: 37,
          max_lon: -119.9,
          max_lat: 37.1,
          centroid_lon: -119.95,
          centroid_lat: 37.05,
          probability: 0.0374,
        },
      },
    ],
  },
  model_version: "v1",
  data_cutoff: "2024-08-21T00:00:00+00:00",
  forecast_window: { start: "2024-08-21T00:00:00+00:00", end: "2024-08-22T00:00:00+00:00", hours: 24 },
  calibration: { method: "isotonic", table: [] },
  evidence: {
    dataset: "wildfire_forecast:v1",
    period_start: "2024-08-21T00:00:00+00:00",
    period_end: "2024-08-22T00:00:00+00:00",
    region_kind: "named",
    region_label: "california",
    region_bbox: [-124.5, 32.5, -114.0, 42.0],
    query_parameters: {},
    processing_version: "0.1.0",
  },
};

async function submit(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: /request forecast/i }));
}

describe("ForecastPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows the real initial status right after creating the job, and disables the form", async () => {
    const user = userEvent.setup();
    mockCreateForecast.mockResolvedValue({ forecast_id: "f-1", status: "PENDING" });
    mockGetForecastStatus.mockResolvedValue({ forecast_id: "f-1", status: "PENDING" });

    render(<ForecastPanel pollIntervalMs={10} />);
    await submit(user);

    const status = await screen.findByRole("status");
    expect(status).toHaveTextContent("Queued");
    expect(status).toHaveTextContent("PENDING");
    expect(screen.getByRole("button", { name: /forecast running/i })).toBeDisabled();
  });

  it("eventually shows the completed job's real result once the backend reports SUCCEEDED", async () => {
    const user = userEvent.setup();
    mockCreateForecast.mockResolvedValue({ forecast_id: "f-1", status: "PENDING" });
    mockGetForecastStatus.mockResolvedValue({ forecast_id: "f-1", status: "SUCCEEDED" });
    mockGetForecastResult.mockResolvedValue({ forecast_id: "f-1", result: RESULT });

    render(<ForecastPanel pollIntervalMs={10} />);
    await submit(user);

    await waitFor(() => {
      expect(screen.getByRole("status")).toHaveTextContent("SUCCEEDED");
    });

    expect(await screen.findByLabelText("Forecast map")).toBeInTheDocument();
    expect(mockGetForecastResult).toHaveBeenCalledWith("f-1");
    expect(screen.getByRole("button", { name: /request forecast/i })).not.toBeDisabled();
  });

  it("shows the real failure reason from the backend, not a fabricated one", async () => {
    const user = userEvent.setup();
    mockCreateForecast.mockResolvedValue({ forecast_id: "f-2", status: "PENDING" });
    mockGetForecastStatus.mockResolvedValue({ forecast_id: "f-2", status: "FAILED" });
    mockGetForecastResult.mockRejectedValue(
      new Error("model prediction failed: no ERA5 hour matched cutoff"),
    );

    render(<ForecastPanel pollIntervalMs={10} />);
    await submit(user);

    await waitFor(() => {
      expect(screen.getByRole("status")).toHaveTextContent("FAILED");
    });
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "model prediction failed: no ERA5 hour matched cutoff",
    );
  });

  it("shows the real submission error when the job cannot even be created", async () => {
    const user = userEvent.setup();
    mockCreateForecast.mockRejectedValue(new Error("region.kind must be one of [...]"));

    render(<ForecastPanel pollIntervalMs={10} />);
    await submit(user);

    expect(await screen.findByRole("alert")).toHaveTextContent("region.kind must be one of [...]");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});
