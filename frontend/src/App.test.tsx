import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import App from "./App";

const mockCreateAnalysis = vi.fn();
const mockGetAnalysisResult = vi.fn();

vi.mock("./api/client", () => ({
  getHealth: vi.fn().mockResolvedValue({ status: "UP" }),
  createAnalysis: (...args: unknown[]) => mockCreateAnalysis(...args),
  getAnalysisResult: (...args: unknown[]) => mockGetAnalysisResult(...args),
}));

const EVIDENCE = {
  dataset: "NASA_FIRMS:VIIRS_SNPP_SP",
  period_start: "2024-08-01T00:00:00+00:00",
  period_end: "2024-08-21T00:00:00+00:00",
  region_kind: "named",
  region_label: "california",
  region_bbox: [-124.5, 32.5, -114.0, 42.0],
  query_parameters: {},
  processing_version: "0.1.0",
};

describe("App", () => {
  it("renders the application shell and backend status", async () => {
    render(<App />);

    expect(
      screen.getByRole("heading", {
        name: /AI Earth Intelligence & Forecasting Engine/i,
      }),
    ).toBeInTheDocument();

    expect(await screen.findByText("Backend: UP")).toBeInTheDocument();
  });

  it("runs a full analysis: submit -> loading -> result with evidence", async () => {
    const user = userEvent.setup();
    mockCreateAnalysis.mockResolvedValue({ id: "abc-123", status: "SUCCEEDED" });
    mockGetAnalysisResult.mockResolvedValue({
      id: "abc-123",
      result: { count: 198 },
      evidence: EVIDENCE,
    });

    render(<App />);
    await user.click(screen.getByRole("button", { name: /run analysis/i }));

    expect(await screen.findByTestId("result-count")).toHaveTextContent(
      "198 fire detections",
    );
    expect(mockCreateAnalysis).toHaveBeenCalledWith(
      expect.objectContaining({ operation: "count" }),
    );
    expect(mockGetAnalysisResult).toHaveBeenCalledWith("abc-123");
    expect(screen.getByText("NASA_FIRMS:VIIRS_SNPP_SP")).toBeInTheDocument();
  });

  it("shows an error message when the analysis fails", async () => {
    const user = userEvent.setup();
    mockCreateAnalysis.mockResolvedValue({ id: "abc-123", status: "FAILED" });
    mockGetAnalysisResult.mockRejectedValue(
      new Error("Unsupported operation: 'forecast'"),
    );

    render(<App />);
    await user.click(screen.getByRole("button", { name: /run analysis/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Unsupported operation: 'forecast'",
    );
  });
});
