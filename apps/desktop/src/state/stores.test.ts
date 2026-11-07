import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ConnectionStatus, EventName, IpcClient, PayloadOf } from "../ipc/client";
import { linkCore, loadSetting, saveSetting } from "./core-link";
import {
  MAX_NOTIFICATIONS,
  useConnectionStore,
  useCoreStore,
  useNotificationsStore,
  useSettingsStore,
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
