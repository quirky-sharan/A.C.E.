import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ConnectionStatus, EventName, IpcClient, PayloadOf } from "../ipc/client";
import { makeMessage, makeTask, requestClient } from "../test/tasks";
import {
  answerConfirmation,
  cancelTask,
  linkCore,
  loadSetting,
  saveSetting,
  submitCommand,
} from "./core-link";
import {
  MAX_NOTIFICATIONS,
  MAX_TASKS,
  useConnectionStore,
  useCoreStore,
  useMessagesStore,
  useNotificationsStore,
  useSettingsStore,
  useTasksStore,
} from "./stores";

const asleep = {
  conversation: "asleep",
  game_mode: false,
  offline: false,
  dnd: false,
  paused_overlay: false,
} as const;

/** Just enough of IpcClient for linkCore: listeners plus scripted requests. */
function fakeClient(answers: Record<string, unknown>) {
  const events = new Map<string, (payload: unknown) => void>();
  let statusListener: ((status: ConnectionStatus, detail: string | null) => void) | null = null;
  const requests: [string, unknown][] = [];
  const client = {
    onStatus: (listener: typeof statusListener) => {
      statusListener = listener;
      return () => {};
    },
    onEvent: (name: string, listener: (payload: unknown) => void) => {
      events.set(name, listener);
      return () => events.delete(name);
    },
    request: (method: string, params: unknown) => {
      requests.push([method, params]);
      return method in answers
        ? Promise.resolve(answers[method])
        : Promise.reject(new Error("not connected"));
    },
  };
  return {
    client: client as unknown as IpcClient,
    requests,
    emit<E extends EventName>(name: E, payload: PayloadOf<E>) {
      events.get(name)?.(payload);
    },
    status(status: ConnectionStatus, detail: string | null = null) {
      statusListener?.(status, detail);
    },
  };
}

beforeEach(() => {
  useConnectionStore.setState(useConnectionStore.getInitialState());
  useCoreStore.setState(useCoreStore.getInitialState());
  useSettingsStore.setState(useSettingsStore.getInitialState());
  useNotificationsStore.setState(useNotificationsStore.getInitialState());
  useTasksStore.setState({ tasks: [] });
  useMessagesStore.setState({ messages: [] });
});

describe("linkCore", () => {
  it("fills the stores from the session, state changes and health", async () => {
    const fake = fakeClient({
      "system.health": { overall: "ok", subsystems: [] },
      "settings.get": { key: "verification.mode", found: true, value: "fast" },
    });
    const unlink = linkCore(fake.client);

    fake.status("connected");
    fake.emit("session.ready", { version: "0.0.1", protocol: 1, dev: true, state: asleep });
    await vi.waitFor(() => expect(useCoreStore.getState().health?.overall).toBe("ok"));
    expect(useConnectionStore.getState()).toMatchObject({
      status: "connected",
      coreVersion: "0.0.1",
      dev: true,
    });
    expect(useCoreStore.getState().state?.conversation).toBe("asleep");
    await vi.waitFor(() =>
      expect(useSettingsStore.getState().values["verification.mode"]).toBe("fast"),
    );

    fake.emit("state.changed", {
      state: { ...asleep, conversation: "listening" },
      previous: asleep,
    });
    expect(useCoreStore.getState().state?.conversation).toBe("listening");

    fake.emit("health.changed", {
      subsystem: "desktop",
      status: "degraded",
      previous: "ok",
      detail: null,
    });
    expect(fake.requests.filter(([method]) => method === "system.health")).toHaveLength(2);

    fake.status("reconnecting", "ace-core is restarting or stopping");
    expect(useConnectionStore.getState()).toMatchObject({
      status: "reconnecting",
      detail: "ace-core is restarting or stopping",
    });
    unlink();
  });
});

describe("settings helpers", () => {
  it("treat a missing setting as null and keep the cache when offline", async () => {
    const online = fakeClient({ "settings.get": { key: "k", found: false, value: null } });
    expect(await loadSetting(online.client, "k")).toBeNull();

    useSettingsStore.getState().setValue("k", "cached");
    const offline = fakeClient({});
    expect(await loadSetting(offline.client, "k")).toBe("cached");
  });

  it("save through the core, then cache", async () => {
    const fake = fakeClient({ "settings.set": { key: "ui.theme", saved: true } });
    await saveSetting(fake.client, "ui.theme", "dark");
    expect(fake.requests).toEqual([["settings.set", { key: "ui.theme", value: "dark" }]]);
    expect(useSettingsStore.getState().values["ui.theme"]).toBe("dark");
    await expect(saveSetting(fakeClient({}).client, "x", 1)).rejects.toThrow();
  });
});

describe("notifications", () => {
  it("keep the newest few and dismiss by id", () => {
    const { push, dismiss } = useNotificationsStore.getState();
    const ids = Array.from({ length: MAX_NOTIFICATIONS + 2 }, (_, n) =>
      push({ tone: "info", title: `n${n}` }),
    );
    const titles = () => useNotificationsStore.getState().items.map((item) => item.title);
    expect(titles()).toEqual(["n2", "n3", "n4", "n5"]);
    dismiss(ids[3]);
    expect(titles()).toEqual(["n2", "n4", "n5"]);
  });
});

const DONE = "2026-11-07T12:00:09.000000Z";

describe("tasks and messages", () => {
  it("keep tasks newest first, replaced by id, and capped", () => {
    const { upsert } = useTasksStore.getState();
    upsert(makeTask({ id: "a", created_at: "2026-11-07T12:00:00.000000Z" }));
    upsert(makeTask({ id: "b", created_at: "2026-11-07T12:00:05.000000Z" }));
    upsert(makeTask({ id: "a", status: "succeeded", finished_at: DONE }));
    expect(useTasksStore.getState().tasks.map((task) => [task.id, task.status])).toEqual([
      ["b", "running"],
      ["a", "succeeded"],
    ]);
    for (let n = 0; n < MAX_TASKS + 5; n++) {
      upsert(
        makeTask({
          id: `x${n}`,
          created_at: `2026-11-08T00:00:${String(n % 60).padStart(2, "0")}.${String(n).padStart(6, "0")}Z`,
        }),
      );
    }
    expect(useTasksStore.getState().tasks).toHaveLength(MAX_TASKS);
  });

  it("let a finished task win over an older task.list result", () => {
    useTasksStore.getState().upsert(makeTask({ id: "a", status: "succeeded", finished_at: DONE }));
    useTasksStore
      .getState()
      .merge([
        makeTask({ id: "a" }),
        makeTask({ id: "c", created_at: "2026-11-07T13:00:00.000000Z" }),
      ]);
    expect(useTasksStore.getState().tasks.map((task) => [task.id, task.status])).toEqual([
      ["c", "running"],
      ["a", "succeeded"],
    ]);
  });

  it("add each message once, in time order", () => {
    const { add, merge } = useMessagesStore.getState();
    add(makeMessage({ id: "m2", ts: "2026-11-07T12:00:02.000000Z" }));
    add(makeMessage({ id: "m2", ts: "2026-11-07T12:00:02.000000Z" }));
    merge([makeMessage({ id: "m1", ts: "2026-11-07T12:00:01.000000Z" })]);
    expect(useMessagesStore.getState().messages.map((message) => message.id)).toEqual(["m1", "m2"]);
  });
});

describe("linkCore and S07", () => {
  it("loads recent history on session.ready and follows task, message and setting events", async () => {
    const fake = fakeClient({
      "system.health": { overall: "ok", subsystems: [] },
      "settings.get": { key: "verification.mode", found: true, value: "fast" },
      "task.list": {
        tasks: [
          makeTask({
            id: "old",
            created_at: "2026-11-07T11:00:00.000000Z",
            status: "succeeded",
            finished_at: DONE,
          }),
        ],
      },
      "message.list": { messages: [makeMessage({ id: "m0" })] },
    });
    const unlink = linkCore(fake.client);
    fake.emit("session.ready", { version: "0.0.1", protocol: 1, dev: true, state: asleep });
    await vi.waitFor(() => expect(useTasksStore.getState().tasks).toHaveLength(1));
    expect(useMessagesStore.getState().messages.map((message) => message.id)).toEqual(["m0"]);
    expect(fake.requests).toContainEqual(["task.list", { limit: 50 }]);

    fake.emit("task.created", { task: makeTask({ id: "new" }) });
    fake.emit("task.updated", { task: makeTask({ id: "new", status: "waiting_user" }) });
    fake.emit("task.finished", {
      task: makeTask({ id: "new", status: "succeeded", finished_at: DONE }),
    });
    expect(useTasksStore.getState().tasks[0]).toMatchObject({ id: "new", status: "succeeded" });
    fake.emit("message.created", {
      message: makeMessage({ id: "m1", role: "ace", ts: "2026-11-07T12:00:01.000000Z" }),
    });
    expect(useMessagesStore.getState().messages.map((message) => message.id)).toEqual(["m0", "m1"]);

    await vi.waitFor(() =>
      expect(useSettingsStore.getState().values["verification.mode"]).toBe("fast"),
    );
    const reads = () => fake.requests.filter(([method]) => method === "settings.get").length;
    const before = reads();
    fake.emit("settings.changed", { key: "verification.mode", deleted: false });
    fake.emit("settings.changed", { key: "not.cached.here", deleted: false });
    await vi.waitFor(() => expect(reads()).toBe(before + 1));
    unlink();
  });
});

describe("command helpers", () => {
  it("submit, answer and cancel through the core", async () => {
    const { client, requests } = requestClient({
      "command.submit": { conversation_id: "c", message_id: "m", intent: "unknown", task_id: null },
      "confirm.respond": { accepted: false },
      "task.cancel": { cancelled: true },
    });
    expect((await submitCommand(client, "hi")).intent).toBe("unknown");
    expect(await answerConfirmation(client, "k1", "no")).toBe(false);
    expect(await cancelTask(client, "t1")).toBe(true);
    expect(requests).toEqual([
      ["command.submit", { text: "hi" }],
      ["confirm.respond", { confirmation_id: "k1", answer: "no" }],
      ["task.cancel", { task_id: "t1" }],
    ]);
  });
});
