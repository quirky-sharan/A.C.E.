import { getCurrentWindow } from "@tauri-apps/api/window";
import { useEffect, useState } from "react";

import { ControlCenter } from "./control-center/control-center";
import { IpcClient } from "./ipc/client";
import { OrbWindow } from "./overlay/orb-window";
import { SidebarWindow } from "./overlay/sidebar-window";
import { fetchEndpoint, watchShell } from "./platform/tauri-link";
import { linkCore } from "./state/core-link";

/** Which window this webview is: "control-center", "orb" or "sidebar" (outside ACE: the first). */
export function windowLabel(): string {
  try {
    return getCurrentWindow().label;
  } catch {
    return "control-center";
  }
}

const LABEL = windowLabel();
const OVERLAY = LABEL === "orb" || LABEL === "sidebar";
if (OVERLAY) {
  document.documentElement.classList.add("overlay"); // transparent page (D-55)
}

// Every window keeps its own IPC client for its lifetime, fed into its own stores.
function App() {
  const [client] = useState(() => new IpcClient({ endpoint: fetchEndpoint }));

  useEffect(() => {
    const unlink = linkCore(client);
    const stopShell = watchShell(client);
    client.start();
    return () => {
      stopShell();
      unlink();
      client.stop();
    };
  }, [client]);

  if (LABEL === "orb") return <OrbWindow client={client} />;
  if (LABEL === "sidebar") return <SidebarWindow client={client} />;
  return <ControlCenter client={client} />;
}

export default App;
