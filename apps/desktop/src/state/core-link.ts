// Feeds the stores from the IPC client: connection status, session, state changes, health,
// tasks and the conversation (S07).
// Kept free of Tauri imports so it can be tested with a fake client.

import type { IpcClient } from "../ipc/client";
import type { CommandSubmitResult, JsonValue } from "../ipc/generated";
import {
  useConnectionStore,
  useCoreStore,
  useMessagesStore,
  useSettingsStore,
  useTasksStore,
} from "./stores";

/** How much history a window loads when it (re)connects. */
export const LOAD_TASKS = 50;
export const LOAD_MESSAGES = 100;

/** Settings the Control Center header shows (the verification mode chip, D-09). */
export const HEADER_SETTINGS = ["verification.mode"] as const;

export function linkCore(client: IpcClient): () => void {
  const refreshHealth = () => {
    client
      .request("system.health", {})
      .then((health) => useCoreStore.getState().setHealth(health))
      .catch(() => {
        // Disconnected meanwhile: the next session.ready refreshes it.
      });
  };

  const stops = [
    client.onStatus((status, detail) => {
      useConnectionStore.getState().setStatus(status, detail);
    }),
    client.onEvent("session.ready", (session) => {
      useConnectionStore.getState().setSession(session);
      useCoreStore.getState().setState(session.state);
      refreshHealth();
      for (const key of HEADER_SETTINGS) {
        void loadSetting(client, key);
      }
      void loadHistory(client);
    }),
    client.onEvent("state.changed", (change) => useCoreStore.getState().setState(change.state)),
    client.onEvent("health.changed", refreshHealth),
    client.onEvent("task.created", ({ task }) => useTasksStore.getState().upsert(task)),
    client.onEvent("task.updated", ({ task }) => useTasksStore.getState().upsert(task)),
    client.onEvent("task.finished", ({ task }) => useTasksStore.getState().upsert(task)),
    client.onEvent("message.created", ({ message }) => useMessagesStore.getState().add(message)),
    client.onEvent("settings.changed", ({ key }) => {
      if (key in useSettingsStore.getState().values) void loadSetting(client, key);
    }),
  ];
  return () => stops.forEach((stop) => stop());
}

/** Read a setting from the core into the cache; returns the value (null when not set). */
export async function loadSetting(client: IpcClient, key: string): Promise<JsonValue> {
  try {
    const result = await client.request("settings.get", { key });
    const value = result.found ? result.value : null;
    useSettingsStore.getState().setValue(key, value);
    return value;
  } catch {
    return useSettingsStore.getState().values[key] ?? null;
  }
}

/** Store a setting in the core (audited as "user") and update the cache. */
export async function saveSetting(client: IpcClient, key: string, value: JsonValue): Promise<void> {
  await client.request("settings.set", { key, value });
  useSettingsStore.getState().setValue(key, value);
}

/** Recent tasks and messages from the core, merged into the stores. */
export async function loadHistory(client: IpcClient): Promise<void> {
  try {
    const [tasks, messages] = await Promise.all([
      client.request("task.list", { limit: LOAD_TASKS }),
      client.request("message.list", { limit: LOAD_MESSAGES }),
    ]);
    useTasksStore.getState().merge(tasks.tasks);
    useMessagesStore.getState().merge(messages.messages);
  } catch {
    // Disconnected meanwhile: the next session.ready loads again.
  }
}

/** A typed command, through the same pipeline as voice (FR-IN-3). */
export function submitCommand(client: IpcClient, text: string): Promise<CommandSubmitResult> {
  return client.request("command.submit", { text });
}

/** Answer a confirmation card; false when it was already answered or expired. */
export async function answerConfirmation(
  client: IpcClient,
  confirmationId: string,
  answer: "yes" | "no",
): Promise<boolean> {
  const result = await client.request("confirm.respond", {
    confirmation_id: confirmationId,
    answer,
  });
  return result.accepted;
}

/** Pick an option of a "which one?" question; false when it was already answered or expired. */
export async function answerClarification(
  client: IpcClient,
  clarificationId: string,
  optionId: string,
): Promise<boolean> {
  const result = await client.request("clarify.respond", {
    clarification_id: clarificationId,
    option_id: optionId,
  });
  return result.accepted;
}

/** The Stop button of a task card. */
export async function cancelTask(client: IpcClient, taskId: string): Promise<boolean> {
  return (await client.request("task.cancel", { task_id: taskId })).cancelled;
}
