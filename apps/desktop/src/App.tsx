import { useEffect, useState } from "react";

import { ControlCenter } from "./control-center/control-center";
import { IpcClient } from "./ipc/client";
import { fetchEndpoint, watchShell } from "./platform/tauri-link";
import { linkCore } from "./state/core-link";

// The Control Center window: one IPC client for the window's lifetime, fed into the stores.
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

  return <ControlCenter />;
}

export default App;
