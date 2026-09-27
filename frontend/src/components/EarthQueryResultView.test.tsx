import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { EarthQueryResult, Evidence } from "../api/types";
import { EarthQueryResultView } from "./EarthQueryResultView";

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

function baseResult(overrides: Partial<EarthQueryResult> = {}): EarthQueryResult {
  return {
    question: "How many fires in California?",
    answer: "There were 198 fires (computed).",
    facts: [],
    outputs: {},
    plan: { steps: [] },
    ...overrides,
  };
}

describe("EarthQueryResultView", () => {
  it("always shows the grounded answer, even with no facts", () => {
    render(<EarthQueryResultView result={baseResult()} />);

    expect(screen.getByTestId("ask-earth-answer")).toHaveTextContent(
      "There were 198 fires (computed).",
    );
  });

  it("says when every number in the answer matched the computed results", () => {
    render(
      <EarthQueryResultView
        result={baseResult({
          grounding: { verified: true, checked: 1, unsupported: [], unknown_tags: [] },
        })}
      />,
    );

    expect(screen.getByTestId("grounding")).toHaveTextContent(
      "All 1 numbers in this answer match the computed results.",
    );
  });

  it("warns about a number the results do not contain", () => {
    render(
      <EarthQueryResultView
        result={baseResult({
          grounding: { verified: false, checked: 2, unsupported: ["512"], unknown_tags: [] },
        })}
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent('"512" is not in the results');
  });

  it("renders documentation passages with their source and warns about a bad citation", () => {
    render(
      <EarthQueryResultView
        result={baseResult({
          answer: "There is no login (documented) [docs/cloud-deployment.md].",
          grounding: {
            verified: false,
            checked: 0,
            unsupported: [],
            unknown_tags: [],
            unknown_citations: ["docs/cloud-deployment.md"],
          },
          facts: [
            {
              step_id: "docs",
              category: "documented",
              result: {
                query: "is there a login",
                passages: [
                  {
                    source: "docs/security-baseline.md",
                    heading: "Authentication",
                    text: "The API has no user authentication.",
                    score: 0.03,
                  },
                ],
              },
              evidence: null,
            },
          ],
        })}
      />,
    );

    const passages = screen.getByTestId("result-doc-passages");
    expect(passages).toHaveTextContent("Authentication");
    expect(passages).toHaveTextContent("docs/security-baseline.md");
    expect(passages).toHaveTextContent("The API has no user authentication.");
    expect(screen.getByRole("alert")).toHaveTextContent(
      "docs/cloud-deployment.md was cited but not retrieved",
    );
  });

  it("renders a forecast summary fact with its peak risk and drivers", () => {
    render(
      <EarthQueryResultView
        result={baseResult({
          facts: [
            {
              step_id: "risk",
              category: "predicted",
              result: {
                forecast_id: "f-1",
                model_version: "v1",
                data_cutoff: "2024-08-15T10:00:00+00:00",
                forecast_window: { start: "a", end: "b", hours: 24 },
                cell_count: 1854,
                max_probability: 0.0312,
                mean_probability: 0.0021,
                top_cells: [],
                drivers: [
                  { feature: "previous_30d_count", contribution: 0.91 },
                  { feature: "elevation_m", contribution: 0.6 },
                ],
                explanation_units: "log_odds",
              },
              evidence: null,
            },
          ],
        })}
      />,
    );

    const summary = screen.getByTestId("result-forecast-summary");
    expect(summary).toHaveTextContent("Highest risk 3.1% across 1854 grid cells.");
    expect(summary).toHaveTextContent("Main drivers: Fires in the past 30 days, Elevation.");
  });

  it("renders a count fact with its region, time and evidence", () => {
    render(
      <EarthQueryResultView
        result={baseResult({
          facts: [
            { step_id: "count", category: "computed", result: { count: 198 }, evidence: EVIDENCE },
          ],
        })}
      />,
    );

    const step = screen.getByLabelText("Step count");
    expect(within(step).getByTestId("result-count")).toHaveTextContent("198 fire detections");
    expect(within(step).getByRole("img", { name: /california/i })).toBeInTheDocument();
    expect(step).toHaveTextContent("2024-08-01T00:00:00+00:00");
    expect(step).toHaveTextContent("2024-08-21T00:00:00+00:00");
    expect(step).toHaveTextContent("NASA_FIRMS:VIIRS_SNPP_SP");
  });

  it("renders a daily aggregate fact as a table", () => {
    render(
      <EarthQueryResultView
        result={baseResult({
          facts: [
            {
              step_id: "daily",
              category: "computed",
              result: { daily: [{ date: "2024-08-01", count: 3 }, { date: "2024-08-02", count: 5 }] },
              evidence: EVIDENCE,
            },
          ],
        })}
      />,
    );

    expect(screen.getByText("2024-08-01").closest("tr")).toHaveTextContent("3");
    expect(screen.getByText("2024-08-02").closest("tr")).toHaveTextContent("5");
  });

  it("renders a weekly aggregate fact as a table", () => {
    render(
      <EarthQueryResultView
        result={baseResult({
          facts: [
            {
              step_id: "weekly",
              category: "computed",
              result: { weekly: [{ week_start: "2024-08-04", count: 21 }] },
              evidence: EVIDENCE,
            },
          ],
        })}
      />,
    );

    expect(screen.getByText("2024-08-04").closest("tr")).toHaveTextContent("21");
  });

  it("renders a map fact's feature values", () => {
    render(
      <EarthQueryResultView
        result={baseResult({
          facts: [
            {
              step_id: "map",
              category: "computed",
              result: {
                type: "FeatureCollection",
                features: [
                  {
                    type: "Feature",
                    geometry: { type: "Polygon", coordinates: [] },
                    properties: {
                      value: 12,
                      units: "count",
                      time: { start: "2024-08-01", end: "2024-08-02" },
                      region_kind: "named",
                      region_label: "bay_area",
                    },
                  },
                ],
              },
              evidence: EVIDENCE,
            },
          ],
        })}
      />,
    );

    expect(screen.getByLabelText(/map values/i)).toHaveTextContent("bay_area: 12 count");
  });

  it("renders a get_data fact with no evidence and no region/time section", () => {
    render(
      <EarthQueryResultView
        result={baseResult({
          facts: [
            {
              step_id: "data",
              category: "observed",
              result: {
                source: "NASA_FIRMS",
                product: "VIIRS_SNPP_SP",
                record_count: 1950,
                provenance: {},
              },
              evidence: null,
            },
          ],
        })}
      />,
    );

    const step = screen.getByLabelText("Step data");
    expect(step).toHaveTextContent("1950 records from NASA_FIRMS (VIIRS_SNPP_SP)");
    expect(within(step).queryByRole("img")).not.toBeInTheDocument();
    expect(screen.queryByText(/dataset/i)).not.toBeInTheDocument();
  });

  it("renders a run_forecast fact as a job reference, deferring the grid to the forecast map", () => {
    render(
      <EarthQueryResultView
        result={baseResult({
          facts: [
            {
              step_id: "forecast",
              category: "predicted",
              result: { forecast_id: "f-42", status: "SUCCEEDED" },
              evidence: null,
            },
          ],
        })}
      />,
    );

    const step = screen.getByLabelText("Step forecast");
    expect(step).toHaveTextContent("f-42");
    expect(step).toHaveTextContent("SUCCEEDED");
    expect(step).toHaveTextContent("forecast map");
  });

  it("renders multiple facts, each in its own step", () => {
    render(
      <EarthQueryResultView
        result={baseResult({
          facts: [
            { step_id: "count", category: "computed", result: { count: 1 }, evidence: EVIDENCE },
            {
              step_id: "forecast",
              category: "predicted",
              result: { forecast_id: "f-1", status: "PENDING" },
              evidence: null,
            },
          ],
        })}
      />,
    );

    expect(screen.getByLabelText("Step count")).toBeInTheDocument();
    expect(screen.getByLabelText("Step forecast")).toBeInTheDocument();
  });
});
