import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { useEffect, useState } from "react";

import {
  bannerFor,
  HOTKEY_LABELS,
  hotkeyNotices,
  SHELL_STATUS_EVENT,
  type ShellStatus,
} from "./shell/status";
import "./App.css";

// S04: a plain status page in the window that becomes the Control Center in S05.
function App() {
  const [status, setStatus] = useState<ShellStatus | null>(null);

  useEffect(() => {
    let eventSeen = false;
    const stopListening = listen<ShellStatus>(SHELL_STATUS_EVENT, (event) => {
      eventSeen = true;
      setStatus(event.payload);
    });
    invoke<ShellStatus>("get_shell_status")
      .then((current) => {
        if (!eventSeen) setStatus(current); // an event is newer than this answer
      })
      .catch(() => setStatus(null));
    return () => {
      void stopListening.then((stop) => stop());
    };
  }, []);

  if (status === null) {
    return <main className="shell">Connecting to the ACE shell…</main>;
  }

  const banner = bannerFor(status.core);
  const notices = hotkeyNotices(status.hotkeys);
  return (
    <main className="shell">
      <h1>ACE</h1>
      {banner && (
        <div className={`banner banner-${banner.tone}`} role="status">
          <strong>{banner.title}</strong>
          {banner.detail && <span>{banner.detail}</span>}
        </div>
      )}
      {notices.length > 0 && (
        <div className="banner banner-warning" role="alert">
          <strong>Some hotkeys are not available</strong>
          {notices.map((notice) => (
            <span key={notice}>{notice}</span>
          ))}
        </div>
      )}
      <section>
        <h2>Core</h2>
        <p>
          {status.core.phase}
          {status.core.port !== null && ` · port ${status.core.port}`}
          {status.core.safeMode && " · safe mode"}
          {status.core.restarts > 0 && ` · restarted ${status.core.restarts}×`}
        </p>
      </section>
      <section>
        <h2>Hotkeys</h2>
        <ul>
          {status.hotkeys.map((hotkey) => (
            <li key={hotkey.action}>
              {HOTKEY_LABELS[hotkey.action]}: {hotkey.shortcut ?? "off"}
              {hotkey.shortcut !== null && (hotkey.registered ? " ✓" : " ✗")}
            </li>
          ))}
        </ul>
      </section>
      <section>
        <h2>Start with Windows</h2>
        <p>
          {status.autostart.enabled ? "on" : "off"}
          {status.autostart.error && ` · ${status.autostart.error}`}
        </p>
      </section>
    </main>
  );
}

export default App;
