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
});
