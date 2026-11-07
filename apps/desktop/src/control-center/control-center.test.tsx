import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { useConnectionStore, useCoreStore, useSettingsStore, useShellStore } from "../state/stores";
import { ControlCenter } from "./control-center";
import { PAGES } from "./pages";

const asleep = {
  conversation: "asleep",
  game_mode: false,
  offline: false,
  dnd: true,
  paused_overlay: false,
} as const;

function navButtons() {
  return within(screen.getByRole("navigation", { name: "Control Center pages" })).getAllByRole(
    "button",
  );
}

beforeEach(() => {
  window.location.hash = "";
  useConnectionStore.setState(useConnectionStore.getInitialState());
  useCoreStore.setState(useCoreStore.getInitialState());
  useSettingsStore.setState(useSettingsStore.getInitialState());
  useShellStore.setState(useShellStore.getInitialState());
});

describe("ControlCenter", () => {
  it("lists every §14.5 page, and the gallery only in development builds", () => {
    const { unmount } = render(<ControlCenter dev={false} />);
    expect(navButtons()).toHaveLength(PAGES.length - 1);
    expect(screen.queryByRole("button", { name: /Component gallery/ })).toBeNull();
    unmount();
    render(<ControlCenter dev />);
    expect(navButtons()).toHaveLength(PAGES.length);
  });

  it("shows live core state, connection, mode and health on the dashboard", () => {
    useConnectionStore.setState({ status: "connected", coreVersion: "0.0.1", dev: true });
    useCoreStore.setState({
      state: asleep,
      health: {
        overall: "degraded",
        subsystems: [
          { name: "core", status: "ok", detail: null, since: "t" },
          { name: "desktop", status: "degraded", detail: "Ctrl+Alt+M is taken", since: "t" },
        ],
      },
    });
    useSettingsStore.setState({ values: { "verification.mode": "paranoid" } });
    render(<ControlCenter dev={false} />);

    expect(screen.getByRole("img", { name: "ACE: Asleep" })).toBeTruthy();
    expect(screen.getAllByText("Connected").length).toBeGreaterThan(0);
    expect(screen.getByText("Paranoid")).toBeTruthy();
    const health = screen.getByRole("region", { name: "Health" });
    expect(within(health).getByRole("img", { name: "desktop: degraded" })).toBeTruthy();
    expect(within(health).getByText("Ctrl+Alt+M is taken")).toBeTruthy();
    expect(
      within(screen.getByRole("region", { name: "Core" })).getByText("Do not disturb"),
    ).toBeTruthy();
  });

  it("follows live updates from the stores", () => {
    useCoreStore.setState({ state: asleep });
    render(<ControlCenter dev={false} />);
    act(() => {
      useCoreStore.getState().setState({ ...asleep, conversation: "thinking" });
      useConnectionStore.getState().setStatus("reconnecting", "ace-core is restarting or stopping");
    });
    expect(screen.getByRole("img", { name: "ACE: Thinking" })).toBeTruthy();
    expect(screen.getAllByText("Reconnecting…").length).toBeGreaterThan(0);
    expect(screen.getByText("ace-core is restarting or stopping")).toBeTruthy();
  });

  it("opens stub pages from the navigation and the keyboard", () => {
    render(<ControlCenter dev={false} />);
    fireEvent.click(screen.getByRole("button", { name: /Providers & Keys/ }));
    act(() => {
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    });
    expect(screen.getByRole("main", { name: "Providers & Keys" })).toBeTruthy();
    expect(screen.getByText("This page arrives in stage S15.")).toBeTruthy();

    const current = screen.getByRole("button", { current: "page" });
    fireEvent.keyDown(current, { key: "ArrowDown" });
    act(() => {
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    });
    expect(screen.getByRole("main", { name: "Voice" })).toBeTruthy();
  });

  it("shows the shell banner while the core restarts", () => {
    useShellStore.setState({
      status: {
        core: {
          phase: "restarting",
          safeMode: false,
          restarts: 2,
          recentCrashes: 2,
          retryInMs: 1000,
          lastExitCode: 1,
          message: "ace-core stopped (exit code 1)",
          port: null,
        },
        hotkeys: [],
        autostart: { enabled: false, error: null },
      },
    });
    render(<ControlCenter dev={false} />);
    expect(screen.getByText("The core stopped — restarting in 1 s")).toBeTruthy();
    expect(screen.getByText("ace-core stopped (exit code 1)")).toBeTruthy();
  });
});
