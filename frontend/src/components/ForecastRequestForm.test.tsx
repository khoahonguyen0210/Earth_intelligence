import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ForecastRequestForm } from "./ForecastRequestForm";

describe("ForecastRequestForm", () => {
  it("submits a named-region forecast request with the chosen cutoff, read as UTC", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();

    render(<ForecastRequestForm onSubmit={onSubmit} disabled={false} />);
    await user.click(screen.getByRole("button", { name: /request forecast/i }));

    expect(onSubmit).toHaveBeenCalledWith({
      region: { kind: "named", value: "california" },
      cutoff: "2024-08-21T00:00:00Z",
    });
  });

  it("submits a bbox region when bbox kind is selected", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();

    render(<ForecastRequestForm onSubmit={onSubmit} disabled={false} />);
    await user.selectOptions(screen.getByLabelText(/kind/i), "bbox");
    await user.click(screen.getByRole("button", { name: /request forecast/i }));

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        region: { kind: "bbox", value: [-124.5, 32.5, -114.0, 42.0] },
      }),
    );
  });

  it("submits a coordinates region when coordinates kind is selected", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();

    render(<ForecastRequestForm onSubmit={onSubmit} disabled={false} />);
    await user.selectOptions(screen.getByLabelText(/kind/i), "coordinates");
    await user.click(screen.getByRole("button", { name: /request forecast/i }));

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        region: { kind: "coordinates", value: [37.5, -119.5] },
      }),
    );
  });

  it("disables the submit button while a forecast is already in flight", () => {
    render(<ForecastRequestForm onSubmit={vi.fn()} disabled={true} />);

    expect(screen.getByRole("button", { name: /forecast running/i })).toBeDisabled();
  });
});
