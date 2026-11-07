import { describe, expect, it } from "vitest";

import { bannerFor, hotkeyNotices, type CoreStatus, type HotkeyStatus } from "./status";

const running: CoreStatus = {
  phase: "running",
  safeMode: false,
  restarts: 0,
  recentCrashes: 0,
  retryInMs: null,
  lastExitCode: null,
  message: null,
  port: 50343,
};

describe("bannerFor", () => {
  it("shows nothing while the core runs normally", () => {
    expect(bannerFor(running)).toBeNull();
  });

  it("explains a restart with its wait and reason", () => {
    const banner = bannerFor({
      ...running,
      phase: "restarting",
      restarts: 1,
      retryInMs: 1000,
      message: "ace-core stopped (exit code 1)",
    });
    expect(banner).toEqual({
      tone: "danger",
      title: "The core stopped — restarting in 1 s",
      detail: "ace-core stopped (exit code 1)",
    });
  });

  it("says nothing about a wait when the restart is immediate", () => {
    const banner = bannerFor({ ...running, phase: "restarting", retryInMs: 0 });
    expect(banner?.title).toBe("The core stopped — restarting");
  });

  it("warns about safe mode", () => {
    expect(bannerFor({ ...running, safeMode: true })?.title).toBe("Safe mode");
  });

  it("covers starting, stopping and stopped", () => {
    expect(bannerFor({ ...running, phase: "starting" })?.tone).toBe("info");
    expect(bannerFor({ ...running, phase: "stopping" })?.tone).toBe("info");
    expect(bannerFor({ ...running, phase: "stopped" })?.tone).toBe("danger");
  });
});

describe("hotkeyNotices", () => {
  const hotkey = (overrides: Partial<HotkeyStatus>): HotkeyStatus => ({
    action: "summon",
    shortcut: "Ctrl+Alt+Space",
    registered: true,
    error: null,
    suggestion: null,
    ...overrides,
  });

  it("lists only hotkeys that failed to register", () => {
    const notices = hotkeyNotices([
      hotkey({}),
      hotkey({ action: "mic_mute", shortcut: null, registered: false }), // switched off
      hotkey({
        action: "emergency_stop",
        shortcut: "Ctrl+Alt+Escape",
        registered: false,
        error: "another app already uses this combination",
        suggestion: "Ctrl+Alt+Shift+Escape",
      }),
    ]);
    expect(notices).toEqual([
      "Emergency stop (Ctrl+Alt+Escape): another app already uses this combination. Try Ctrl+Alt+Shift+Escape instead.",
    ]);
  });
});
