import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { RegionMap } from "./RegionMap";

describe("RegionMap", () => {
  it("renders an svg map labeled with the region", () => {
    render(
      <RegionMap
        bbox={[-124.5, 32.5, -114.0, 42.0]}
        label="california"
      />,
    );

    expect(
      screen.getByRole("img", { name: /map of queried region: california/i }),
    ).toBeInTheDocument();
  });

  it("renders without a label suffix when label is null", () => {
    render(<RegionMap bbox={[-124.5, 32.5, -114.0, 42.0]} label={null} />);

    expect(
      screen.getByRole("img", { name: "Map of queried region" }),
    ).toBeInTheDocument();
  });

  it("renders the region rectangle within the svg", () => {
    const { container } = render(
      <RegionMap bbox={[-120.0, 37.0, -119.0, 38.0]} label="test" />,
    );

    const regionRect = container.querySelector(
      '[data-testid="region-map-region"]',
    );

    expect(regionRect).not.toBeNull();
    expect(Number(regionRect?.getAttribute("width"))).toBeGreaterThan(0);
    expect(Number(regionRect?.getAttribute("height"))).toBeGreaterThan(0);
  });

  it("renders lat/lon graticule lines so it reads as a map, not a flat block", () => {
    const { container } = render(
      <RegionMap bbox={[-124.5, 32.5, -114.0, 42.0]} label="california" />,
    );

    const lines = container.querySelectorAll("line");

    expect(lines.length).toBeGreaterThan(0);
  });

  it("renders axis tick labels for scale reference", () => {
    render(<RegionMap bbox={[-124.5, 32.5, -114.0, 42.0]} label="california" />);

    expect(screen.getByText("-120")).toBeInTheDocument();
  });

  it("keeps the reference outline visible even when the region fills the entire frame", () => {
    const { container } = render(
      <RegionMap bbox={[-124.5, 32.5, -114.0, 42.0]} label="california" />,
    );

    const strokeOnlyRects = Array.from(
      container.querySelectorAll("rect"),
    ).filter((rect) => rect.getAttribute("fill") === "none");

    expect(strokeOnlyRects.length).toBeGreaterThan(0);
  });
});
