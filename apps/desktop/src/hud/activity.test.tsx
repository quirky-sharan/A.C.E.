import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ConversationState } from "../ipc/generated";
import { IDLE_MS, useOrbAnimating, useSettled } from "./activity";

function stubReducedMotion(matches: boolean): void {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches,
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  }));
}

beforeEach(() => {
  vi.useFakeTimers();
  stubReducedMotion(false);
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("useSettled", () => {
  it("turns true only after the value stayed the same long enough", () => {
    const { result, rerender } = renderHook(({ value }) => useSettled(value, 1000), {
      initialProps: { value: "a" as string | null },
    });
    expect(result.current).toBe(false);
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(result.current).toBe(true);
    rerender({ value: "b" });
    expect(result.current).toBe(false);
    act(() => {
      vi.advanceTimersByTime(999);
    });
    expect(result.current).toBe(false);
    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(result.current).toBe(true);
  });
});

describe("useOrbAnimating", () => {
  const render = (state: ConversationState | null) =>
    renderHook(({ value }) => useOrbAnimating(value), { initialProps: { value: state } });

  it("animates an asleep orb for a few seconds, then rests", () => {
    const { result } = render("asleep");
    expect(result.current).toBe(true);
    act(() => {
      vi.advanceTimersByTime(IDLE_MS);
    });
    expect(result.current).toBe(false);
  });

  it("keeps animating while ACE is busy", () => {
    const { result } = render("listening");
    act(() => {
      vi.advanceTimersByTime(IDLE_MS * 4);
    });
    expect(result.current).toBe(true);
  });

  it("never animates with reduced motion", () => {
    stubReducedMotion(true);
    const { result } = render("thinking");
    expect(result.current).toBe(false);
  });

  it("never animates while the window is hidden", () => {
    const visibility = vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden");
    const { result } = render("thinking");
    expect(result.current).toBe(false);
    visibility.mockReturnValue("visible");
    act(() => {
      document.dispatchEvent(new Event("visibilitychange"));
    });
    expect(result.current).toBe(true);
  });
});
