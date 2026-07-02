import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import App from "./App";

vi.mock("./api/client", () => ({
  getHealth: vi.fn().mockResolvedValue({ status: "UP" }),
}));

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
});