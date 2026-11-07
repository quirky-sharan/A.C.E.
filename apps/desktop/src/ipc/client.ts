// The UI's connection to ace-core (ACE_MASTER_PLAN.md §5.5, S05 task 2): WebSocket to 127.0.0.1,
// the token as the first message, typed requests with id correlation, typed events, and automatic
// reconnects with backoff. The endpoint (port + token) is fetched again for every attempt, because
// each core run has a new port and a new token (D-52). The token never goes into a URL or a log.

import type { AceIpc } from "./generated";

export type MethodName = keyof AceIpc["methods"];
export type ParamsOf<M extends MethodName> = AceIpc["methods"][M]["params"];
export type ResultOf<M extends MethodName> = AceIpc["methods"][M]["result"];
export type EventName = keyof AceIpc["events"];
export type PayloadOf<E extends EventName> = AceIpc["events"][E];

export type ConnectionStatus = "idle" | "connecting" | "connected" | "reconnecting" | "stopped";

export interface Endpoint {
  port: number;
  token: string;
}

export interface IpcClientOptions {
  /** Where the core listens right now (the `get_ipc_info` Tauri command). */
  endpoint: () => Promise<Endpoint>;
  createSocket?: (url: string) => WebSocket;
  /** Wait before reconnect attempt `n` (0-based). */
  reconnectDelayMs?: (attempt: number) => number;
  requestTimeoutMs?: number;
}

export class IpcError extends Error {
  readonly code: string;
  readonly details: Record<string, unknown>;

  constructor(code: string, message: string, details: Record<string, unknown> = {}) {
    super(message);
    this.name = "IpcError";
    this.code = code;
    this.details = details;
  }
}

/** 0.25 s, 0.5 s, 1 s, 2 s, 4 s, then 5 s. The core itself is back within ~3 s (D-52). */
export function reconnectDelay(attempt: number): number {
  return Math.min(250 * 2 ** attempt, 5000);
}

const SOCKET_OPEN = 1;

interface Pending {
  resolve: (result: unknown) => void;
  reject: (error: Error) => void;
  timer: ReturnType<typeof setTimeout>;
}

type StatusListener = (status: ConnectionStatus, detail: string | null) => void;

export class IpcClient {
  private readonly options: Required<IpcClientOptions>;
  private socket: WebSocket | null = null;
  private status: ConnectionStatus = "idle";
  private running = false;
  private connectedOnce = false;
  private attempt = 0;
  private generation = 0;
  private retryTimer: ReturnType<typeof setTimeout> | null = null;
  private nextId = 1;
  private readonly pending = new Map<string, Pending>();
  private readonly eventListeners = new Map<string, Set<(payload: unknown) => void>>();
  private readonly statusListeners = new Set<StatusListener>();

  constructor(options: IpcClientOptions) {
    this.options = {
      createSocket: (url) => new WebSocket(url),
      reconnectDelayMs: reconnectDelay,
      requestTimeoutMs: 10_000,
      ...options,
    };
  }

  get currentStatus(): ConnectionStatus {
    return this.status;
  }

  start(): void {
    if (this.running) return;
    this.running = true;
    void this.connect();
  }

  stop(): void {
    this.running = false;
    this.generation += 1; // ignore everything the old socket still reports
    this.clearRetry();
    this.closeSocket("client stopped");
    this.failPending("the connection was stopped");
    this.setStatus("stopped", null);
  }

  /** Try again right away, e.g. when the shell reports a freshly started core. */
  reconnectNow(): void {
    if (!this.running || this.status === "connected") return;
    this.clearRetry();
    this.attempt = 0;
    void this.connect();
  }

  request<M extends MethodName>(method: M, params: ParamsOf<M>): Promise<ResultOf<M>> {
    const socket = this.socket;
    if (this.status !== "connected" || socket === null || socket.readyState !== SOCKET_OPEN) {
      return Promise.reject(new IpcError("E_UI_NOT_CONNECTED", "not connected to ace-core"));
    }
    const id = `ui-${this.nextId++}`;
    return new Promise<ResultOf<M>>((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new IpcError("E_UI_TIMEOUT", `${method} got no answer in time`));
      }, this.options.requestTimeoutMs);
      this.pending.set(id, {
        // The core validated the result against the same schema these types come from.
        resolve: (result) => resolve(result as ResultOf<M>),
        reject,
        timer,
      });
      socket.send(JSON.stringify({ v: 1, type: "request", id, method, params }));
    });
  }

  onEvent<E extends EventName>(name: E, listener: (payload: PayloadOf<E>) => void): () => void {
    const listeners = this.eventListeners.get(name) ?? new Set();
    this.eventListeners.set(name, listeners);
    const wrapped = listener as (payload: unknown) => void;
    listeners.add(wrapped);
    return () => listeners.delete(wrapped);
  }

  onStatus(listener: StatusListener): () => void {
    this.statusListeners.add(listener);
    return () => this.statusListeners.delete(listener);
  }

  // ---- connection ----

  private async connect(): Promise<void> {
    if (!this.running) return;
    const generation = ++this.generation;
    this.closeSocket("reconnecting");
    this.setStatus(this.connectedOnce ? "reconnecting" : "connecting", null);

    let endpoint: Endpoint;
    try {
      endpoint = await this.options.endpoint();
    } catch (error) {
      if (generation === this.generation) this.scheduleReconnect(describe(error));
      return;
    }
    if (!this.running || generation !== this.generation) return;

    const socket = this.options.createSocket(`ws://127.0.0.1:${endpoint.port}/ws`);
    this.socket = socket;
    socket.onopen = () => {
      if (generation !== this.generation) return;
      socket.send(JSON.stringify({ v: 1, type: "auth", token: endpoint.token }));
    };
    socket.onmessage = (event: MessageEvent) => {
      if (generation === this.generation) this.handleMessage(event.data);
    };
    socket.onclose = (event: CloseEvent) => {
      if (generation !== this.generation) return;
      this.socket = null;
      this.failPending("the connection to ace-core closed");
      this.scheduleReconnect(closeDetail(event));
    };
    socket.onerror = () => {
      // A close event always follows; it schedules the reconnect.
    };
  }

  private scheduleReconnect(detail: string): void {
    if (!this.running) return;
    const delay = this.options.reconnectDelayMs(this.attempt);
    this.attempt += 1;
    this.setStatus("reconnecting", detail);
    this.clearRetry();
    this.retryTimer = setTimeout(() => {
      this.retryTimer = null;
      void this.connect();
    }, delay);
  }

  private handleMessage(raw: unknown): void {
    if (typeof raw !== "string") return;
    let message: unknown;
    try {
      message = JSON.parse(raw);
    } catch {
      return;
    }
    if (!isRecord(message)) return;

    if (message.type === "event" && typeof message.method === "string") {
      if (message.method === "session.ready") {
        this.attempt = 0;
        this.connectedOnce = true;
        this.setStatus("connected", null);
      }
      this.eventListeners.get(message.method)?.forEach((listener) => listener(message.params));
      return;
    }
    if (
      (message.type === "response" || message.type === "error") &&
      typeof message.id === "string"
    ) {
      const pending = this.pending.get(message.id);
      if (pending === undefined) return;
      this.pending.delete(message.id);
      clearTimeout(pending.timer);
      if (message.type === "response") {
        pending.resolve(message.result);
      } else {
        const info = isRecord(message.error) ? message.error : {};
        pending.reject(
          new IpcError(
            typeof info.code === "string" ? info.code : "E_IPC_INTERNAL",
            typeof info.message === "string" ? info.message : "request failed",
            isRecord(info.details) ? info.details : {},
          ),
        );
      }
    }
  }

  private setStatus(status: ConnectionStatus, detail: string | null): void {
    this.status = status;
    this.statusListeners.forEach((listener) => listener(status, detail));
  }

  private failPending(reason: string): void {
    for (const [id, pending] of this.pending) {
      clearTimeout(pending.timer);
      pending.reject(new IpcError("E_UI_DISCONNECTED", reason));
      this.pending.delete(id);
    }
  }

  private closeSocket(reason: string): void {
    const socket = this.socket;
    this.socket = null;
    if (socket !== null) {
      socket.onopen = null;
      socket.onmessage = null;
      socket.onclose = null;
      socket.onerror = null;
      socket.close(1000, reason);
    }
  }

  private clearRetry(): void {
    if (this.retryTimer !== null) {
      clearTimeout(this.retryTimer);
      this.retryTimer = null;
    }
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function describe(error: unknown): string {
  if (error instanceof Error) return error.message;
  return typeof error === "string" ? error : "unknown error";
}

function closeDetail(event: CloseEvent): string {
  switch (event.code) {
    case 4401:
      return "ace-core refused the token";
    case 1001:
      return "ace-core is restarting or stopping";
    default:
      return event.reason || `connection closed (${event.code})`;
  }
}
