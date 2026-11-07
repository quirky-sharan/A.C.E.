// The only place the UI talks to the Tauri shell: the IPC endpoint (`get_ipc_info`, §5.6 step 4)
// and the shell's status (`get_shell_status` + the `ace://shell-status` event, D-52). Outside the
// ACE app (e.g. the gallery in a normal browser) both calls fail quietly and the UI stays offline.

import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";

import type { Endpoint, IpcClient } from "../ipc/client";
import { SHELL_STATUS_EVENT, type ShellStatus } from "../shell/status";
import { useShellStore } from "../state/stores";

export function fetchEndpoint(): Promise<Endpoint> {
  return invoke<Endpoint>("get_ipc_info");
}

/** Mirror the shell's status into the store; reconnect at once when a new core is running. */
export function watchShell(client: IpcClient): () => void {
  let active = true;
  let lastPort: number | null = null;
  const apply = (status: ShellStatus) => {
    if (!active) return;
    useShellStore.getState().setStatus(status);
    if (status.core.phase === "running" && status.core.port !== lastPort) {
      lastPort = status.core.port;
      client.reconnectNow();
    }
  };
  const stopListening = listen<ShellStatus>(SHELL_STATUS_EVENT, (event) =>
    apply(event.payload),
  ).catch(() => () => {});
  invoke<ShellStatus>("get_shell_status")
    .then((status) => {
      if (useShellStore.getState().status === null) apply(status); // an event may be newer
    })
    .catch(() => {});
  return () => {
    active = false;
    void stopListening.then((stop) => stop());
  };
}
