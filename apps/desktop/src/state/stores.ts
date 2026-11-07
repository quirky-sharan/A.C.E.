// UI state (S05 task 3): one small Zustand store per domain (§17.2). Stores only hold data and
// simple setters; `core-link.ts` feeds them from the IPC client and the desktop shell.

import { create } from "zustand";

import type { ConnectionStatus } from "../ipc/client";
import type { CoreStateInfo, HealthResult, JsonValue, SessionReadyPayload } from "../ipc/generated";
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

// ---- tasks (filled from S07 on) ----

export type StepStatus = "pending" | "running" | "done" | "warning" | "failed" | "retrying";

export interface TaskStep {
  id: string;
  label: string;
  status: StepStatus;
}

export interface TaskSummary {
  id: string;
  title: string;
  status:
    "queued" | "running" | "waiting_user" | "verifying" | "succeeded" | "failed" | "cancelled";
  steps: TaskStep[];
}

export interface TasksState {
  tasks: TaskSummary[];
  setTasks: (tasks: TaskSummary[]) => void;
}

export const useTasksStore = create<TasksState>()((set) => ({
  tasks: [],
  setTasks: (tasks) => set({ tasks }),
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
