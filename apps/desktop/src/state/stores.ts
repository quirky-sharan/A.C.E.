// UI state (S05 task 3): one small Zustand store per domain (§17.2). Stores only hold data and
// simple setters; `core-link.ts` feeds them from the IPC client and the desktop shell.

import { create } from "zustand";

import type { ConnectionStatus } from "../ipc/client";
import type {
  CoreStateInfo,
  HealthResult,
  JsonValue,
  MessageInfo,
  SessionReadyPayload,
  TaskInfo,
} from "../ipc/generated";
import type { ShellStatus } from "../shell/status";

// ---- connection to ace-core ----

export interface ConnectionState {
  status: ConnectionStatus;
  detail: string | null;
  coreVersion: string | null;
  dev: boolean;
  setStatus: (status: ConnectionStatus, detail: string | null) => void;
  setSession: (session: SessionReadyPayload) => void;
}

export const useConnectionStore = create<ConnectionState>()((set) => ({
  status: "idle",
  detail: null,
  coreVersion: null,
  dev: false,
  setStatus: (status, detail) => set({ status, detail }),
  setSession: (session) => set({ coreVersion: session.version, dev: session.dev }),
}));

// ---- what ACE is doing (conversation state, flags, health) ----

export interface CoreViewState {
  state: CoreStateInfo | null;
  health: HealthResult | null;
  setState: (state: CoreStateInfo) => void;
  setHealth: (health: HealthResult) => void;
  clear: () => void;
}

export const useCoreStore = create<CoreViewState>()((set) => ({
  state: null,
  health: null,
  setState: (state) => set({ state }),
  setHealth: (health) => set({ health }),
  clear: () => set({ state: null, health: null }),
}));

// ---- tasks and the conversation (S07: from the core's command pipeline) ----

/** How a step looks in a StepList (§14.3 badges); `toStepView` maps the core's step states. */
export type StepStatus = "pending" | "running" | "done" | "warning" | "failed" | "retrying";

export interface TaskStep {
  id: string;
  label: string;
  status: StepStatus;
}

/** Tasks kept in memory per window (newest first); History asks the core for older ones. */
export const MAX_TASKS = 100;
/** Messages kept in memory per window (oldest first). */
export const MAX_MESSAGES = 200;

const newestFirst = (a: TaskInfo, b: TaskInfo) =>
  a.created_at < b.created_at ? 1 : a.created_at > b.created_at ? -1 : 0;

export interface TasksState {
  tasks: TaskInfo[];
  /** A task event: insert or replace by id. */
  upsert: (task: TaskInfo) => void;
  /** A task.list result. A task that already finished here keeps its newer state. */
  merge: (tasks: TaskInfo[]) => void;
}

export const useTasksStore = create<TasksState>()((set) => ({
  tasks: [],
  upsert: (task) =>
    set((state) => ({
      tasks: [task, ...state.tasks.filter((entry) => entry.id !== task.id)]
        .sort(newestFirst)
        .slice(0, MAX_TASKS),
    })),
  merge: (tasks) =>
    set((state) => {
      const known = new Map(state.tasks.map((task) => [task.id, task]));
      for (const task of tasks) {
        const current = known.get(task.id);
        if (current?.finished_at && !task.finished_at) continue; // an event was newer
        known.set(task.id, task);
      }
      return { tasks: [...known.values()].sort(newestFirst).slice(0, MAX_TASKS) };
    }),
}));

export interface MessagesState {
  messages: MessageInfo[];
  add: (message: MessageInfo) => void;
  merge: (messages: MessageInfo[]) => void;
}

const byTime = (a: MessageInfo, b: MessageInfo) => (a.ts < b.ts ? -1 : a.ts > b.ts ? 1 : 0);

export const useMessagesStore = create<MessagesState>()((set) => ({
  messages: [],
  add: (message) =>
    set((state) =>
      state.messages.some((entry) => entry.id === message.id)
        ? state
        : { messages: [...state.messages, message].sort(byTime).slice(-MAX_MESSAGES) },
    ),
  merge: (messages) =>
    set((state) => {
      const all = new Map(state.messages.map((message) => [message.id, message]));
      for (const message of messages) all.set(message.id, message);
      return { messages: [...all.values()].sort(byTime).slice(-MAX_MESSAGES) };
    }),
}));

// ---- in-app notifications (toasts) ----

export type Tone = "info" | "success" | "warning" | "danger";

export interface Notification {
  id: number;
  tone: Tone;
  title: string;
  message?: string;
}

export interface NotificationsState {
  items: Notification[];
  push: (notification: Omit<Notification, "id">) => number;
  dismiss: (id: number) => void;
}

/** At most this many toasts at once; the oldest goes first. */
export const MAX_NOTIFICATIONS = 4;
let nextNotificationId = 1;

export const useNotificationsStore = create<NotificationsState>()((set) => ({
  items: [],
  push: (notification) => {
    const id = nextNotificationId++;
    set((state) => ({
      items: [...state.items, { ...notification, id }].slice(-MAX_NOTIFICATIONS),
    }));
    return id;
  },
  dismiss: (id) => set((state) => ({ items: state.items.filter((item) => item.id !== id) })),
}));

// ---- settings cache (the core's settings table is the source of truth) ----

export interface SettingsState {
  values: Record<string, JsonValue>;
  setValue: (key: string, value: JsonValue) => void;
}

export const useSettingsStore = create<SettingsState>()((set) => ({
  values: {},
  setValue: (key, value) => set((state) => ({ values: { ...state.values, [key]: value } })),
}));

// ---- the desktop shell's own status (core supervision, hotkeys, autostart) ----

export interface ShellState {
  status: ShellStatus | null;
  setStatus: (status: ShellStatus) => void;
}

export const useShellStore = create<ShellState>()((set) => ({
  status: null,
  setStatus: (status) => set({ status }),
}));
