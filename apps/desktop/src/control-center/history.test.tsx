import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useTasksStore } from "../state/stores";
import { makeStep, makeTask, requestClient } from "../test/tasks";
import { History } from "./history";

beforeEach(() => {
  useTasksStore.setState({ tasks: [] });
});

describe("History", () => {
  it("lists tasks newest first with their steps, tiers and replies", () => {
    useTasksStore.setState({
      tasks: [
        makeTask({
          id: "b",
          utterance: "demo forbidden",
          intent: "demo.forbidden",
          status: "failed",
          error_code: "E_SUPERVISOR_FORBIDDEN",
          finished_at: "2026-11-07T12:00:06.000000Z",
          result_summary: "I can't do that one, boss.",
          steps: [
            makeStep({
              skill_id: "demo.forbidden",
              label: "Run the demo forbidden action",
              tier: "T3",
              status: "refused",
            }),
          ],
        }),
        makeTask({
          id: "a",
          utterance: "echo hello",
          intent: "system.echo",
          status: "succeeded",
          finished_at: "2026-11-07T12:00:01.000000Z",
          result_summary: "hello",
          steps: [makeStep({ skill_id: "system.echo", tier: "T0", status: "succeeded" })],
        }),
      ],
    });
    render(<History client={null} />);
    const list = screen.getByRole("list", { name: "Tasks" }).textContent ?? "";
    expect(list.indexOf("demo forbidden")).toBeLessThan(list.indexOf("echo hello"));
    for (const text of ["Refused", "T3", "E_SUPERVISOR_FORBIDDEN", "I can't do that one, boss."]) {
      expect(list).toContain(text);
    }
    expect(list).toContain("Done");
    expect(screen.getAllByRole("img", { name: "failed" })).toHaveLength(1);
    expect(screen.getAllByRole("img", { name: "done" })).toHaveLength(1);
  });

  it("explains where tasks come from while there are none", () => {
    render(<History client={null} />);
    expect(screen.getByText(/No tasks yet\. Type a command in the sidebar/)).toBeTruthy();
  });

  it("searches through the core after a short pause", async () => {
    const { client, requests } = requestClient({
      "task.list": { tasks: [makeTask({ id: "x", utterance: "open spotify" })] },
    });
    render(<History client={client} />);
    fireEvent.change(screen.getByRole("searchbox", { name: "Search tasks" }), {
      target: { value: " spotify " },
    });
    expect(requests).toEqual([]); // waits for the typing to pause
    await vi.waitFor(() =>
      expect(requests).toEqual([["task.list", { limit: 100, query: "spotify" }]]),
    );
    await vi.waitFor(() => expect(screen.getByText("open spotify")).toBeTruthy());
  });

  it("says when nothing matches, and when the search fails", async () => {
    const { client } = requestClient({ "task.list": { tasks: [] } });
    const { unmount } = render(<History client={client} />);
    fireEvent.change(screen.getByRole("searchbox", { name: "Search tasks" }), {
      target: { value: "nothing" },
    });
    await vi.waitFor(() => expect(screen.getByText("No tasks match.")).toBeTruthy());
    unmount();
    render(<History client={requestClient().client} />);
    fireEvent.change(screen.getByRole("searchbox", { name: "Search tasks" }), {
      target: { value: "x" },
    });
    await vi.waitFor(() => expect(screen.getByText("Search failed: not connected")).toBeTruthy());
  });
});
