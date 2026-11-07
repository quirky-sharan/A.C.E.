import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  IpcClient,
  IpcError,
  reconnectDelay,
  type ConnectionStatus,
  type Endpoint,
} from "./client";

/** A WebSocket stand-in the tests drive by hand. */
class FakeSocket {
  static all: FakeSocket[] = [];
  readonly url: string;
  readonly sent: Record<string, unknown>[] = [];
  readyState = 0;
  closedWith: number | null = null;
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    FakeSocket.all.push(this);
  }

  send(data: string): void {
    this.sent.push(JSON.parse(data) as Record<string, unknown>);
  }

  close(code = 1000): void {
    this.closedWith = code;
    this.readyState = 3;
  }

  // ---- test controls ----
  open(): void {
    this.readyState = 1;
    this.onopen?.(new Event("open"));
  }

  receive(message: Record<string, unknown>): void {
    this.onmessage?.({ data: JSON.stringify(message) } as MessageEvent);
  }

  ready(): void {
    this.open();
    this.receive({
      v: 1,
      type: "event",
      method: "session.ready",
      params: { version: "0.0.1", protocol: 1, dev: true, state: { conversation: "asleep" } },
      ts: "2026-11-07T00:00:00Z",
    });
  }

  drop(code = 1006, reason = ""): void {
    this.readyState = 3;
    this.onclose?.({ code, reason } as CloseEvent);
  }
}

function latest(): FakeSocket {
  const socket = FakeSocket.all.at(-1);
  if (socket === undefined) throw new Error("no socket was created");
  return socket;
}

function makeClient(endpoints: Endpoint[] | (() => Promise<Endpoint>)) {
  const statuses: [ConnectionStatus, string | null][] = [];
  let call = 0;
  const endpoint =
    typeof endpoints === "function"
      ? endpoints
      : () => Promise.resolve(endpoints[Math.min(call++, endpoints.length - 1)]);
  const client = new IpcClient({
    endpoint,
    createSocket: (url) => new FakeSocket(url) as unknown as WebSocket,
    requestTimeoutMs: 1000,
  });
  client.onStatus((status, detail) => statuses.push([status, detail]));
  return { client, statuses };
}

/** Let pending promise callbacks (the endpoint lookup) run. */
async function settle(): Promise<void> {
  await vi.advanceTimersByTimeAsync(0);
}

beforeEach(() => {
  FakeSocket.all = [];
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("IpcClient", () => {
  it("authenticates with the token first and is connected after session.ready", async () => {
    const { client, statuses } = makeClient([{ port: 50343, token: "t".repeat(64) }]);
    const ready = vi.fn();
    client.onEvent("session.ready", ready);
    client.start();
    await settle();
    const socket = latest();
    expect(socket.url).toBe("ws://127.0.0.1:50343/ws"); // the token never goes into the URL
    socket.open();
    expect(socket.sent).toEqual([{ v: 1, type: "auth", token: "t".repeat(64) }]);
    expect(client.currentStatus).toBe("connecting");
    socket.ready();
    expect(client.currentStatus).toBe("connected");
    expect(ready).toHaveBeenCalledWith(expect.objectContaining({ version: "0.0.1" }));
    expect(statuses.map(([status]) => status)).toEqual(["connecting", "connected"]);
  });

  it("matches responses and errors to their requests", async () => {
    const { client } = makeClient([{ port: 1, token: "x".repeat(64) }]);
    client.start();
    await settle();
    latest().ready();

    const health = client.request("system.health", {});
    const setting = client.request("settings.get", { key: "" });
    const [first, second] = latest().sent.slice(1);
    expect(first).toEqual({
      v: 1,
      type: "request",
      id: "ui-1",
      method: "system.health",
      params: {},
    });
    expect(second).toMatchObject({ id: "ui-2", method: "settings.get", params: { key: "" } });

    latest().receive({
      v: 1,
      type: "error",
      id: "ui-2",
      method: "settings.get",
      error: { code: "E_IPC_BAD_PARAMS", message: "invalid params", details: { errors: [] } },
      ts: "t",
    });
    latest().receive({
      v: 1,
      type: "response",
      id: "ui-1",
      method: "system.health",
      result: { overall: "ok", subsystems: [] },
      ts: "t",
    });
    await expect(health).resolves.toEqual({ overall: "ok", subsystems: [] });
    await expect(setting).rejects.toMatchObject({ code: "E_IPC_BAD_PARAMS" });
  });

  it("rejects requests while disconnected and when they time out", async () => {
    const { client } = makeClient([{ port: 1, token: "x".repeat(64) }]);
    await expect(client.request("system.health", {})).rejects.toBeInstanceOf(IpcError);
    client.start();
    await settle();
    latest().ready();
    const late = client.request("system.health", {});
    const assertion = expect(late).rejects.toMatchObject({ code: "E_UI_TIMEOUT" });
    await vi.advanceTimersByTimeAsync(1000);
    await assertion;
  });

  it("delivers events to their listeners until they unsubscribe", async () => {
    const { client } = makeClient([{ port: 1, token: "x".repeat(64) }]);
    const seen: string[] = [];
    const stop = client.onEvent("state.changed", (payload) =>
      seen.push(payload.state.conversation),
    );
    client.start();
    await settle();
    latest().ready();
    const changed = (conversation: string) =>
      latest().receive({
        v: 1,
        type: "event",
        method: "state.changed",
        params: { state: { conversation }, previous: { conversation: "asleep" } },
        ts: "t",
      });
    changed("listening");
    stop();
    changed("thinking");
    expect(seen).toEqual(["listening"]);
  });

  it("reconnects with backoff and a fresh endpoint after the core restarts", async () => {
    const { client, statuses } = makeClient([
      { port: 1001, token: "a".repeat(64) },
      { port: 1002, token: "b".repeat(64) },
    ]);
    client.start();
    await settle();
    latest().ready();
    const pending = client.request("system.health", {});
    const failed = expect(pending).rejects.toMatchObject({ code: "E_UI_DISCONNECTED" });

    latest().drop(1001, "ace-core is stopping");
    await failed;
    expect(client.currentStatus).toBe("reconnecting");
    expect(statuses.at(-1)).toEqual(["reconnecting", "ace-core is restarting or stopping"]);
    expect(FakeSocket.all).toHaveLength(1);

    await vi.advanceTimersByTimeAsync(reconnectDelay(0));
    expect(FakeSocket.all).toHaveLength(2);
    const second = latest();
    expect(second.url).toBe("ws://127.0.0.1:1002/ws");
    second.open();
    expect(second.sent[0]).toEqual({ v: 1, type: "auth", token: "b".repeat(64) });
    second.ready();
    expect(client.currentStatus).toBe("connected");
  });

  it("keeps retrying while the core is down, each wait longer", async () => {
    let calls = 0;
    const { client } = makeClient(() => {
      calls += 1;
      return Promise.reject(new Error("ace-core is not running"));
    });
    client.start();
    await settle();
    expect(calls).toBe(1);
    await vi.advanceTimersByTimeAsync(250);
    expect(calls).toBe(2);
    await vi.advanceTimersByTimeAsync(499);
    expect(calls).toBe(2);
    await vi.advanceTimersByTimeAsync(1);
    expect(calls).toBe(3);
    expect(client.currentStatus).toBe("reconnecting");
    client.stop();
    await vi.advanceTimersByTimeAsync(10_000);
    expect(calls).toBe(3);
    expect(client.currentStatus).toBe("stopped");
  });

  it("reconnectNow skips the wait", async () => {
    let calls = 0;
    const { client } = makeClient(() => {
      calls += 1;
      return calls === 1
        ? Promise.reject(new Error("not yet"))
        : Promise.resolve({ port: 7, token: "z".repeat(64) });
    });
    client.start();
    await settle();
    client.reconnectNow();
    await settle();
    expect(calls).toBe(2);
    expect(latest().url).toBe("ws://127.0.0.1:7/ws");
  });

  it("stop closes the socket and ignores what it reports afterwards", async () => {
    const { client } = makeClient([{ port: 1, token: "x".repeat(64) }]);
    client.start();
    await settle();
    const socket = latest();
    socket.ready();
    client.stop();
    expect(socket.closedWith).toBe(1000);
    socket.drop();
    await vi.advanceTimersByTimeAsync(10_000);
    expect(FakeSocket.all).toHaveLength(1);
    expect(client.currentStatus).toBe("stopped");
  });

  it("backoff grows to five seconds", () => {
    expect([0, 1, 2, 3, 4, 5, 6].map(reconnectDelay)).toEqual([
      250, 500, 1000, 2000, 4000, 5000, 5000,
    ]);
  });
});
