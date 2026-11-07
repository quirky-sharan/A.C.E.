// Feeds the stores from the IPC client: connection status, session, state changes and health.
// Kept free of Tauri imports so it can be tested with a fake client.

import type { IpcClient } from "../ipc/client";
import type { JsonValue } from "../ipc/generated";
import { useConnectionStore, useCoreStore, useSettingsStore } from "./stores";

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
    }),
    client.onEvent("state.changed", (change) => useCoreStore.getState().setState(change.state)),
    client.onEvent("health.changed", refreshHealth),
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
