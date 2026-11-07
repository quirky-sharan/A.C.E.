// What the desktop shell reports about itself (Rust: src-tauri/src/status.rs). It arrives from the
// `get_shell_status` command and then as the `ace://shell-status` event on every change (S04).

export const SHELL_STATUS_EVENT = "ace://shell-status";

export type CorePhase = "starting" | "running" | "restarting" | "stopping" | "stopped";

export interface CoreStatus {
  phase: CorePhase;
  safeMode: boolean;
  restarts: number;
  recentCrashes: number;
  retryInMs: number | null;
  lastExitCode: number | null;
  message: string | null;
  port: number | null;
}

export type HotkeyAction =
  "summon" | "push_to_talk" | "emergency_stop" | "toggle_overlay" | "mic_mute";

export interface HotkeyStatus {
  action: HotkeyAction;
  shortcut: string | null;
  registered: boolean;
  error: string | null;
  suggestion: string | null;
}

export interface AutostartStatus {
  enabled: boolean;
  error: string | null;
}

export interface ShellStatus {
  core: CoreStatus;
  hotkeys: HotkeyStatus[];
  autostart: AutostartStatus;
}

export const HOTKEY_LABELS: Record<HotkeyAction, string> = {
  summon: "Summon sidebar",
  push_to_talk: "Push-to-talk (hold)",
  emergency_stop: "Emergency stop",
  toggle_overlay: "Hide / show overlay",
  mic_mute: "Mute mic",
};

export interface Banner {
  tone: "info" | "warning" | "danger";
  title: string;
  detail: string | null;
}

/** The banner shown while the core is not simply running (S04 task 4), or null. */
export function bannerFor(core: CoreStatus): Banner | null {
  switch (core.phase) {
    case "running":
      return core.safeMode
        ? {
            tone: "warning",
            title: "Safe mode",
            detail:
              "The core crashed 5 times in 5 minutes, so optional features stay off until ACE restarts. Diagnostics will show the details.",
          }
        : null;
    case "starting":
      return { tone: "info", title: "Starting the ACE core…", detail: null };
    case "restarting": {
      const wait = core.retryInMs ? ` in ${Math.ceil(core.retryInMs / 1000)} s` : "";
      return {
        tone: "danger",
        title: `The core stopped — restarting${wait}`,
        detail: core.message,
      };
    }
    case "stopping":
      return { tone: "info", title: "Stopping the ACE core…", detail: null };
    case "stopped":
      return { tone: "danger", title: "The ACE core is stopped", detail: core.message };
  }
}

/** One line per hotkey that could not be registered, with the suggested alternative. */
export function hotkeyNotices(hotkeys: HotkeyStatus[]): string[] {
  return hotkeys
    .filter((hotkey) => hotkey.shortcut !== null && !hotkey.registered)
    .map((hotkey) => {
      const hint = hotkey.suggestion ? ` Try ${hotkey.suggestion} instead.` : "";
      return `${HOTKEY_LABELS[hotkey.action]} (${hotkey.shortcut ?? ""}): ${hotkey.error ?? "not registered"}.${hint}`;
    });
}
