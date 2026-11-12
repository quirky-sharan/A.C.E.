import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { IpcClient } from "../ipc/client";
import { useConnectionStore, useCoreStore, useMessagesStore, useTasksStore } from "../state/stores";
import {
  makeClarification,
  makeConfirmation,
  makeMessage,
  makeStep,
  makeTask,
  requestClient,
} from "../test/tasks";
import { OrbWindow, DRAG_THRESHOLD } from "./orb-window";
import { ORB_EVENT, SIDEBAR_EVENT, type SidebarEvent } from "./overlay-api";
import { SidebarWindow } from "./sidebar-window";

const mocks = vi.hoisted(() => ({
  invoke: vi.fn<(...args: unknown[]) => Promise<unknown>>(() => Promise.resolve(null)),
  listeners: new Map<string, (event: { payload: unknown }) => void>(),
}));

vi.mock("@tauri-apps/api/core", () => ({
  invoke: (...args: unknown[]) => mocks.invoke(...args),
}));
vi.mock("@tauri-apps/api/event", () => ({
  listen: (name: string, handler: (event: { payload: unknown }) => void) => {
    mocks.listeners.set(name, handler);
    return Promise.resolve(() => mocks.listeners.delete(name));
  },
}));

const asleep = {
  conversation: "asleep",
  game_mode: false,
  offline: false,
  dnd: false,
  paused_overlay: false,
} as const;

function calls(command: string) {
  return mocks.invoke.mock.calls.filter(([name]) => name === command);
}

/** What the shell answers; `overlay_state` says the orb is showing. */
function respond(overrides: Record<string, unknown> = {}) {
  mocks.invoke.mockImplementation((command: unknown) => {
    const answers: Record<string, unknown> = {
      overlay_state: { orbVisible: true, sidebarOpen: false, edge: "right" },
      ...overrides,
    };
    return Promise.resolve(
      typeof command === "string" && command in answers ? answers[command] : null,
    );
  });
}

beforeEach(() => {
  mocks.invoke.mockClear();
  respond();
  mocks.listeners.clear();
  useCoreStore.setState({ state: asleep, health: null });
  useTasksStore.setState({ tasks: [] });
  useMessagesStore.setState({ messages: [] });
  useConnectionStore.setState(useConnectionStore.getInitialState());
});

describe("OrbWindow", () => {
  it("reports its hit area and opens the sidebar on a click", async () => {
    render(<OrbWindow client={null} />);
    const orb = await screen.findByRole("button", { name: "Open the ACE sidebar" });
    await vi.waitFor(() =>
      expect(calls("overlay_hit_rects").at(-1)?.[1]).toMatchObject({ rects: [expect.any(Object)] }),
    );
    fireEvent.pointerDown(orb, { button: 0, pointerId: 1, screenX: 10, screenY: 10 });
    fireEvent.pointerUp(orb, { button: 0, pointerId: 1, screenX: 11, screenY: 11 });
    expect(calls("overlay_orb_clicked")).toHaveLength(1);
    expect(screen.getByRole("img", { name: "ACE: Asleep" })).toBeTruthy();
  });

  it("opens the Control Center on right-click", async () => {
    render(<OrbWindow client={null} />);
    fireEvent.contextMenu(await screen.findByRole("button", { name: "Open the ACE sidebar" }));
    expect(calls("open_control_center")).toHaveLength(1);
  });

  it("drags along the edge and saves the new position in the core", async () => {
    respond({ overlay_drag: 0.3 });
    const request = vi.fn(() => Promise.resolve({ key: "overlay.orb_y", saved: true }));
    render(<OrbWindow client={{ request } as unknown as IpcClient} />);
    const orb = await screen.findByRole("button", { name: "Open the ACE sidebar" });
    fireEvent.pointerDown(orb, { button: 0, pointerId: 1, screenX: 10, screenY: 10 });
    fireEvent.pointerMove(orb, { pointerId: 1, screenX: 10, screenY: 10 + DRAG_THRESHOLD + 2 });
    fireEvent.pointerUp(orb, { pointerId: 1, screenX: 10, screenY: 80 });
    expect(calls("overlay_drag").map(([, args]) => args)).toEqual([
      { phase: "start" },
      { phase: "end" },
    ]);
    expect(calls("overlay_orb_clicked")).toHaveLength(0); // a drag is not a click
    await vi.waitFor(() =>
      expect(request).toHaveBeenCalledWith("settings.set", { key: "overlay.orb_y", value: 0.3 }),
    );
  });
});

describe("OrbWindow visibility", () => {
  it("draws nothing and is fully click-through while hidden", async () => {
    render(<OrbWindow client={null} />);
    await screen.findByRole("button", { name: "Open the ACE sidebar" });
    act(() => {
      mocks.listeners.get(ORB_EVENT)?.({ payload: { visible: false } });
    });
    expect(screen.queryByRole("button", { name: "Open the ACE sidebar" })).toBeNull();
    await vi.waitFor(() => expect(calls("overlay_hit_rects").at(-1)?.[1]).toEqual({ rects: [] }));
  });
});

describe("SidebarWindow", () => {
  const open = (payload: Partial<SidebarEvent> = {}) =>
    act(() => {
      mocks.listeners.get(SIDEBAR_EVENT)?.({
        payload: { open: true, focus: false, edge: "right", ...payload },
      });
    });

  it("shows every §14.3 section, with placeholders until their stages", async () => {
    useConnectionStore.setState({ status: "connected" });
    render(<SidebarWindow />);
    await vi.waitFor(() => expect(mocks.listeners.has(SIDEBAR_EVENT)).toBe(true));
    open();
    expect(screen.getByRole("complementary", { name: "ACE sidebar" })).toBeTruthy();
    for (const name of ["Conversation", "Current task", "Background jobs"]) {
      expect(screen.getByRole("region", { name })).toBeTruthy();
    }
    expect(screen.getByText("No task running.")).toBeTruthy();
    expect(screen.getByRole("textbox", { name: "Command" })).toBeTruthy();
    expect(screen.getByRole("img", { name: "internet: ok" })).toBeTruthy();
    expect(screen.getByRole("img", { name: "microphone: arrives in S09" })).toBeTruthy();
  });

  it("draws nothing while closed", async () => {
    render(<SidebarWindow />);
    await vi.waitFor(() => expect(mocks.listeners.has(SIDEBAR_EVENT)).toBe(true));
    expect(screen.queryByRole("complementary", { name: "ACE sidebar" })).toBeNull();
    await vi.waitFor(() => expect(calls("overlay_hit_rects").at(-1)?.[1]).toEqual({ rects: [] }));
  });

  it("shows the running task with its steps, and Stop cancels it", async () => {
    useTasksStore.setState({
      tasks: [makeTask({ steps: [makeStep({ label: "Launch it", status: "succeeded" })] })],
    });
    const { client, requests } = requestClient({ "task.cancel": { cancelled: true } });
    render(<SidebarWindow client={client} />);
    await vi.waitFor(() => expect(mocks.listeners.has(SIDEBAR_EVENT)).toBe(true));
    open();
    expect(screen.getByRole("region", { name: "Current task" }).textContent).toContain(
      "open spotify",
    );
    expect(screen.getByRole("img", { name: "done" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Stop" }));
    expect(requests).toEqual([["task.cancel", { task_id: "t1" }]]);
  });

  it("shows the last finished task when nothing runs", async () => {
    useTasksStore.setState({
      tasks: [
        makeTask({
          status: "succeeded",
          finished_at: "2026-11-07T12:00:01.000000Z",
          steps: [makeStep({ status: "succeeded" })],
        }),
      ],
    });
    render(<SidebarWindow client={requestClient().client} />);
    await vi.waitFor(() => expect(mocks.listeners.has(SIDEBAR_EVENT)).toBe(true));
    open();
    const card = screen.getByRole("region", { name: "Current task" });
    expect(card.textContent).toContain("Last task");
    expect(card.textContent).toContain("Done");
    expect(screen.getByRole<HTMLButtonElement>("button", { name: "Stop" }).disabled).toBe(true);
  });

  it("shows the conversation with a ✓ on a finished task's reply", async () => {
    useTasksStore.setState({
      tasks: [makeTask({ id: "t9", status: "succeeded", finished_at: "2026-11-07T12:00:01Z" })],
    });
    useMessagesStore.setState({
      messages: [
        makeMessage({ id: "m1", text: "echo hello" }),
        makeMessage({
          id: "m2",
          role: "ace",
          text: "hello",
          detail: 'Echo: "hello"',
          task_id: "t9",
          ts: "2026-11-07T12:00:01.000000Z",
        }),
      ],
    });
    render(<SidebarWindow />);
    await vi.waitFor(() => expect(mocks.listeners.has(SIDEBAR_EVENT)).toBe(true));
    open();
    const chat = screen.getByRole("region", { name: "Conversation" });
    expect(chat.textContent).toContain("echo hello");
    expect(chat.textContent).toContain('Echo: "hello"');
    expect(within(chat).getByRole("img", { name: "Done" }).textContent).toBe("✓");
  });

  it("shows confirmation cards with a countdown and answers through the core", async () => {
    useTasksStore.setState({
      tasks: [makeTask({ status: "waiting_user", confirmation: makeConfirmation() })],
    });
    const { client, requests } = requestClient({ "confirm.respond": { accepted: true } });
    render(<SidebarWindow client={client} />);
    await vi.waitFor(() => expect(mocks.listeners.has(SIDEBAR_EVENT)).toBe(true));
    open();
    const cards = screen.getByRole("region", { name: "Confirmations" });
    expect(cards.textContent).toContain("Run the demo dangerous action");
    expect(cards.textContent).toMatch(/Cancels by itself in (29|30) s/);
    fireEvent.click(within(cards).getByRole("button", { name: "Yes" }));
    await vi.waitFor(() =>
      expect(requests).toEqual([["confirm.respond", { confirmation_id: "k1", answer: "yes" }]]),
    );
  });

  it("focuses the input when summoned and reports the time", async () => {
    render(<SidebarWindow />);
    await vi.waitFor(() => expect(mocks.listeners.has(SIDEBAR_EVENT)).toBe(true));
    open({ focus: true });
    expect(document.activeElement).toBe(screen.getByRole("textbox", { name: "Command" }));
    expect(calls("overlay_report_focus")).toHaveLength(1);
  });

  it("takes focus for typing only when the input is clicked", async () => {
    render(<SidebarWindow />);
    await vi.waitFor(() => expect(mocks.listeners.has(SIDEBAR_EVENT)).toBe(true));
    open();
    expect(calls("overlay_focus_input")).toHaveLength(0);
    fireEvent.pointerDown(screen.getByRole("textbox", { name: "Command" }));
    expect(calls("overlay_focus_input")).toHaveLength(1);
  });

  it("starts a confirmation's countdown when it appears, not when the sidebar opened", async () => {
    render(<SidebarWindow client={requestClient().client} />);
    await vi.waitFor(() => expect(mocks.listeners.has(SIDEBAR_EVENT)).toBe(true));
    open();
    const later = Date.now() + 40_000;
    const clock = vi.spyOn(Date, "now").mockReturnValue(later);
    try {
      act(() => {
        useTasksStore.setState({
          tasks: [
            makeTask({
              status: "waiting_user",
              confirmation: makeConfirmation({
                expires_at: new Date(later + 30_000).toISOString(),
              }),
            }),
          ],
        });
      });
      const cards = screen.getByRole("region", { name: "Confirmations" });
      expect(cards.textContent).toContain("Cancels by itself in 30 s");
    } finally {
      clock.mockRestore();
    }
  });

  it("puts a task's badge on its final reply only", async () => {
    useTasksStore.setState({
      tasks: [makeTask({ id: "t5", status: "succeeded", finished_at: "2026-11-07T12:00:09Z" })],
    });
    useMessagesStore.setState({
      messages: [
        makeMessage({ id: "q", role: "ace", text: "Should I go ahead?", task_id: "t5" }),
        makeMessage({
          id: "r",
          role: "ace",
          text: "Done.",
          task_id: "t5",
          ts: "2026-11-07T12:00:09.000000Z",
        }),
      ],
    });
    render(<SidebarWindow />);
    await vi.waitFor(() => expect(mocks.listeners.has(SIDEBAR_EVENT)).toBe(true));
    open();
    const badges = within(screen.getByRole("region", { name: "Conversation" })).getAllByRole(
      "img",
      { name: "Done" },
    );
    expect(badges).toHaveLength(1);
    expect(badges[0].parentElement?.textContent).toBe("✓Done.");
  });

  it("asks which one with a card, and a click answers through the core", async () => {
    useTasksStore.setState({
      tasks: [makeTask({ status: "waiting_user", clarification: makeClarification() })],
    });
    const { client, requests } = requestClient({ "clarify.respond": { accepted: true } });
    render(<SidebarWindow client={client} />);
    await vi.waitFor(() => expect(mocks.listeners.has(SIDEBAR_EVENT)).toBe(true));
    open();
    const cards = screen.getByRole("region", { name: "Questions" });
    expect(cards.textContent).toContain("Which python did you mean?");
    fireEvent.click(within(cards).getByRole("button", { name: "Python 3.12 (64-bit)" }));
    await vi.waitFor(() =>
      expect(requests).toEqual([
        ["clarify.respond", { clarification_id: "q1", option_id: "py312" }],
      ]),
    );
    expect(calls("overlay_allow_foreground")).toHaveLength(1); // the chosen app may come to the front
  });

  it("sends typed commands to the core and keeps history", async () => {
    const { client, requests } = requestClient({
      "command.submit": {
        conversation_id: "c1",
        message_id: "m1",
        intent: "apps.open",
        task_id: "t1",
      },
    });
    render(<SidebarWindow client={client} />);
    await vi.waitFor(() => expect(mocks.listeners.has(SIDEBAR_EVENT)).toBe(true));
    open();
    const input = screen.getByRole<HTMLInputElement>("textbox", { name: "Command" });
    fireEvent.change(input, { target: { value: "open spotify" } });
    fireEvent.keyDown(input, { key: "Enter" });
    await vi.waitFor(() =>
      expect(requests).toEqual([["command.submit", { text: "open spotify" }]]),
    );
    expect(calls("overlay_allow_foreground")).toHaveLength(1); // granted before the command
    fireEvent.keyDown(input, { key: "ArrowUp" });
    expect(input.value).toBe("open spotify");
  });

  it("says so when a command cannot be sent", async () => {
    render(<SidebarWindow />);
    await vi.waitFor(() => expect(mocks.listeners.has(SIDEBAR_EVENT)).toBe(true));
    open();
    const input = screen.getByRole<HTMLInputElement>("textbox", { name: "Command" });
    fireEvent.change(input, { target: { value: "help" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(screen.getByText(/Not connected to ACE's core yet/)).toBeTruthy();
  });

  it("footer buttons mute the mic and hide the overlay for an hour", async () => {
    render(<SidebarWindow />);
    await vi.waitFor(() => expect(mocks.listeners.has(SIDEBAR_EVENT)).toBe(true));
    open();
    fireEvent.click(screen.getByRole("button", { name: "Mute mic" }));
    fireEvent.click(screen.getByRole("button", { name: "Hide for 1 hour" }));
    expect(calls("overlay_input").map(([, args]) => args)).toEqual([{ action: "mic_mute" }]);
    expect(calls("overlay_hide_for").map(([, args]) => args)).toEqual([{ minutes: 60 }]);
  });

  it("Esc closes through the shell at once and hides the window after the slide-out", async () => {
    render(<SidebarWindow />);
    await vi.waitFor(() => expect(mocks.listeners.has(SIDEBAR_EVENT)).toBe(true));
    open();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(calls("overlay_close_sidebar")).toHaveLength(1); // the focus goes back right away
    expect(calls("overlay_sidebar_hidden")).toHaveLength(0); // still sliding out
    await vi.waitFor(() => expect(calls("overlay_sidebar_hidden")).toHaveLength(1), {
      timeout: 3000,
    });
    expect(screen.queryByRole("complementary", { name: "ACE sidebar" })).toBeNull();
  });

  it("the close button works like Esc", async () => {
    render(<SidebarWindow />);
    await vi.waitFor(() => expect(mocks.listeners.has(SIDEBAR_EVENT)).toBe(true));
    open();
    fireEvent.click(screen.getByRole("button", { name: "Close the sidebar" }));
    expect(calls("overlay_close_sidebar")).toHaveLength(1);
    await vi.waitFor(() => expect(calls("overlay_sidebar_hidden")).toHaveLength(1), {
      timeout: 3000,
    });
  });

  it("hides the window after a close that came from the shell", async () => {
    render(<SidebarWindow />);
    await vi.waitFor(() => expect(mocks.listeners.has(SIDEBAR_EVENT)).toBe(true));
    open();
    open({ open: false });
    await vi.waitFor(() => expect(calls("overlay_sidebar_hidden")).toHaveLength(1), {
      timeout: 3000,
    });
    expect(calls("overlay_close_sidebar")).toHaveLength(0); // the shell already closed it
    expect(screen.queryByRole("complementary", { name: "ACE sidebar" })).toBeNull();
  });
});
