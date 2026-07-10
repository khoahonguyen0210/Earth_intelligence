import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Evidence } from "../api/types";
import { ResultView } from "./ResultView";

const EVIDENCE: Evidence = {
  dataset: "NASA_FIRMS:VIIRS_SNPP_SP",
  period_start: "2024-08-01T00:00:00+00:00",
  period_end: "2024-08-21T00:00:00+00:00",
  region_kind: "named",
  region_label: "california",
  region_bbox: [-124.5, 32.5, -114.0, 42.0],
  query_parameters: { question: "test", intent: "count", operation: "count" },
  processing_version: "0.1.0",
};

describe("ResultView", () => {
  it("renders a count result", () => {
    render(<ResultView result={{ count: 198 }} evidence={EVIDENCE} />);

    expect(screen.getByTestId("result-count")).toHaveTextContent(
      "198 fire detections",
    );
  });

  it("renders a daily aggregate result as a table", () => {
    render(
      <ResultView
        result={{
          daily: [
            { date: "2024-08-01", count: 3 },
            { date: "2024-08-02", count: 0 },
          ],
        }}
        evidence={EVIDENCE}
      />,
    );

    expect(screen.getByText("Daily fire counts")).toBeInTheDocument();
    expect(screen.getByText("2024-08-01")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("renders a weekly aggregate result as a table", () => {
    render(
      <ResultView
        result={{ weekly: [{ week_start: "2024-07-29", count: 5 }] }}
        evidence={EVIDENCE}
      />,
    );

    expect(screen.getByText("Weekly fire counts")).toBeInTheDocument();
    expect(screen.getByText("2024-07-29")).toBeInTheDocument();
  });

  it("renders a map result as a feature list", () => {
    render(
      <ResultView
        result={{
          type: "FeatureCollection",
          features: [
            {
              type: "Feature",
              geometry: { type: "Polygon", coordinates: [] },
              properties: {
                value: 198,
                time: { start: "a", end: "b" },
                units: "fire_count",
                region_kind: "named",
                region_label: "california",
              },
            },
          ],
        }}
        evidence={EVIDENCE}
      />,
    );

    expect(screen.getByText(/california: 198 fire_count/)).toBeInTheDocument();
  });

  it("always renders the region map and evidence panel", () => {
    render(<ResultView result={{ count: 1 }} evidence={EVIDENCE} />);

    expect(
      screen.getByRole("img", { name: /map of queried region: california/i }),
    ).toBeInTheDocument();
    expect(screen.getByText("NASA_FIRMS:VIIRS_SNPP_SP")).toBeInTheDocument();
    expect(screen.getByText("0.1.0")).toBeInTheDocument();
  });
});
