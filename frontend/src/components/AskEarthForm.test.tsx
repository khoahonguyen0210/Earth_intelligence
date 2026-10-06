import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AskEarthForm } from "./AskEarthForm";

describe("AskEarthForm", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("submits the typed question", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();

    render(<AskEarthForm onSubmit={onSubmit} disabled={false} />);
    await user.type(
      screen.getByLabelText(/ask earth a question/i),
      "How many fires occurred in California last week?",
    );
    await user.click(screen.getByRole("button", { name: /^ask$/i }));

    expect(onSubmit).toHaveBeenCalledWith("How many fires occurred in California last week?");
  });

  it("does not submit a blank or whitespace-only question", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();

    render(<AskEarthForm onSubmit={onSubmit} disabled={false} />);
    await user.type(screen.getByLabelText(/ask earth a question/i), "   ");
    await user.click(screen.getByRole("button", { name: /^ask$/i }));

    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("disables the submit button and shows the loading label while asking", () => {
    render(<AskEarthForm onSubmit={vi.fn()} disabled={true} />);

    expect(screen.getByRole("button", { name: /asking earth/i })).toBeDisabled();
  });

  it("shows no recent queries before anything has been asked", () => {
    render(<AskEarthForm onSubmit={vi.fn()} disabled={false} />);

    expect(screen.queryByLabelText(/recent queries/i)).not.toBeInTheDocument();
  });

  it("remembers a submitted question as a recent query, most recent first", async () => {
    const user = userEvent.setup();

    const { unmount } = render(<AskEarthForm onSubmit={vi.fn()} disabled={false} />);
    await user.type(screen.getByLabelText(/ask earth a question/i), "first question");
    await user.click(screen.getByRole("button", { name: /^ask$/i }));
    unmount();

    render(<AskEarthForm onSubmit={vi.fn()} disabled={false} />);
    await user.type(screen.getByLabelText(/ask earth a question/i), "second question");
    await user.click(screen.getAllByRole("button", { name: /^ask$/i })[0]);

    const recent = screen.getByLabelText(/recent queries/i);
    const items = within(recent).getAllByRole("button");
    expect(items.map((item) => item.textContent)).toEqual(["second question", "first question"]);
  });

  it("clicking a recent query fills the input without submitting it", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();

    const { rerender } = render(<AskEarthForm onSubmit={onSubmit} disabled={false} />);
    await user.type(screen.getByLabelText(/ask earth a question/i), "earlier question");
    await user.click(screen.getByRole("button", { name: /^ask$/i }));
    onSubmit.mockClear();
    rerender(<AskEarthForm onSubmit={onSubmit} disabled={false} />);

    await user.click(screen.getByRole("button", { name: "earlier question" }));

    expect(screen.getByLabelText(/ask earth a question/i)).toHaveValue("earlier question");
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("deduplicates a re-asked question instead of listing it twice", async () => {
    const user = userEvent.setup();

    render(<AskEarthForm onSubmit={vi.fn()} disabled={false} />);
    for (const question of ["repeat me", "something else", "repeat me"]) {
      await user.clear(screen.getByLabelText(/ask earth a question/i));
      await user.type(screen.getByLabelText(/ask earth a question/i), question);
      await user.click(screen.getByRole("button", { name: /^ask$/i }));
    }

    const items = within(screen.getByLabelText(/recent queries/i)).getAllByRole("button");
    expect(items.map((item) => item.textContent)).toEqual(["repeat me", "something else"]);
  });
});
