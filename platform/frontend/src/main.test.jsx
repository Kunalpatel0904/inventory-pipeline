import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { App } from "./main.jsx";

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
    ok: true,
    json: async () => [{ id: 1, content: "Ship safer previews", created_at: "2026-01-01T10:00:00Z" }],
  }));
});

test("loads and displays ideas", async () => {
  render(<App />);
  expect(await screen.findByText("Ship safer previews")).toBeTruthy();
  expect(screen.getByText("Community ideas")).toBeTruthy();
});

test("submits a new idea and shows confirmation", async () => {
  fetch.mockImplementationOnce(async () => ({ ok: true, json: async () => [] }))
    .mockImplementationOnce(async () => ({
      ok: true,
      json: async () => ({ id: 2, content: "Add safer deploys", created_at: "2026-01-01T10:00:00Z" }),
    }));
  render(<App />);
  const input = screen.getByLabelText("What should we build next?");
  fireEvent.change(input, { target: { value: "Add safer deploys" } });
  fireEvent.submit(input.closest("form"));
  expect(await screen.findByText("Add safer deploys")).toBeTruthy();
  expect(await screen.findByText("Idea submitted successfully.")).toBeTruthy();
});
