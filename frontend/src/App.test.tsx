import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";

const mockCreateEarthQuery = vi.fn();
const mockGetEarthQueryResult = vi.fn();

vi.mock("./api/client", () => ({
  getHealth: vi.fn().mockResolvedValue({ status: "UP" }),
  createEarthQuery: (...args: unknown[]) => mockCreateEarthQuery(...args),
  getEarthQueryResult: (...args: unknown[]) => mockGetEarthQueryResult(...args),
}));

describe("App", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("renders the application shell and backend status", async () => {
    render(<App />);

    expect(
      screen.getByRole("heading", {
        name: /ask earth about wildfire risk/i,
      }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /ai earth intelligence/i })).toBeInTheDocument();

    expect(await screen.findByText("Backend: UP")).toBeInTheDocument();
  });

  it("asks a natural-language question end to end: submit -> loading -> grounded answer", async () => {
    const user = userEvent.setup();
    mockCreateEarthQuery.mockResolvedValue({ id: "abc-123", status: "SUCCEEDED" });
    mockGetEarthQueryResult.mockResolvedValue({
      id: "abc-123",
      result: {
        question: "How many fires in California?",
        answer: "There were 198 fires (computed).",
        facts: [{ step_id: "count", category: "computed", result: { count: 198 }, evidence: null }],
        outputs: { count: { count: 198 } },
        plan: { steps: [] },
      },
    });

    render(<App />);
    await user.type(
      screen.getByLabelText(/ask earth a question/i),
      "How many fires in California?",
    );
    await user.click(screen.getByRole("button", { name: /^ask$/i }));

    expect(await screen.findByTestId("ask-earth-answer")).toHaveTextContent(
      "There were 198 fires (computed).",
    );
    expect(mockCreateEarthQuery).toHaveBeenCalledWith("How many fires in California?");
    expect(mockGetEarthQueryResult).toHaveBeenCalledWith("abc-123");
    expect(screen.getByLabelText(/facts behind this answer/i)).toHaveTextContent("count (computed)");
    expect(screen.getByTestId("result-count")).toHaveTextContent("198 fire detections");
  });

  it("shows an error message when the query fails", async () => {
    const user = userEvent.setup();
    mockCreateEarthQuery.mockResolvedValue({ id: "abc-123", status: "FAILED" });
    mockGetEarthQueryResult.mockRejectedValue(new Error("invalid region: unknown named region"));

    render(<App />);
    await user.type(screen.getByLabelText(/ask earth a question/i), "fires in atlantis?");
    await user.click(screen.getByRole("button", { name: /^ask$/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "invalid region: unknown named region",
    );
  });

  it("disables the form while a question is being asked", async () => {
    const user = userEvent.setup();
    let resolveQuery: (value: { id: string; status: string }) => void = () => {};
    mockCreateEarthQuery.mockReturnValue(new Promise((resolve) => { resolveQuery = resolve; }));

    render(<App />);
    await user.type(screen.getByLabelText(/ask earth a question/i), "How many fires?");
    await user.click(screen.getByRole("button", { name: /^ask$/i }));

    expect(await screen.findByRole("status")).toHaveTextContent("Asking Earth...");
    expect(screen.getByRole("button", { name: /asking earth/i })).toBeDisabled();

    resolveQuery({ id: "abc-123", status: "SUCCEEDED" });
  });
});
