import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { QueryForm } from "./QueryForm";

describe("QueryForm", () => {
  it("submits a named-region count request by default", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();

    render(<QueryForm onSubmit={onSubmit} disabled={false} />);
    await user.click(screen.getByRole("button", { name: /run analysis/i }));

    expect(onSubmit).toHaveBeenCalledWith({
      question: "How many fires occurred in California?",
      intent: "count",
      region: { kind: "named", value: "california" },
      time_range: { start: "2024-08-01", end: "2024-08-20" },
      operation: "count",
    });
  });

  it("derives intent from the selected operation", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();

    render(<QueryForm onSubmit={onSubmit} disabled={false} />);
    await user.selectOptions(
      screen.getByLabelText(/operation/i),
      "daily_aggregate",
    );
    await user.click(screen.getByRole("button", { name: /run analysis/i }));

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({ intent: "aggregate", operation: "daily_aggregate" }),
    );
  });

  it("submits a bbox region when bbox kind is selected", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();

    render(<QueryForm onSubmit={onSubmit} disabled={false} />);
    await user.selectOptions(screen.getByLabelText(/^kind$/i), "bbox");
    await user.click(screen.getByRole("button", { name: /run analysis/i }));

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        region: { kind: "bbox", value: [-124.5, 32.5, -114.0, 42.0] },
      }),
    );
  });

  it("submits a coordinates region when coordinates kind is selected", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();

    render(<QueryForm onSubmit={onSubmit} disabled={false} />);
    await user.selectOptions(screen.getByLabelText(/^kind$/i), "coordinates");
    await user.click(screen.getByRole("button", { name: /run analysis/i }));

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        region: { kind: "coordinates", value: [37.5, -119.5] },
      }),
    );
  });

  it("disables the submit button while disabled prop is true", () => {
    render(<QueryForm onSubmit={vi.fn()} disabled={true} />);

    expect(screen.getByRole("button", { name: /running/i })).toBeDisabled();
  });
});
