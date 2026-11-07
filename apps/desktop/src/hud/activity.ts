// When the HUD may animate (§14.4, D-14, NFR-2): only while the window is visible, the user allows
// motion (Windows "animation effects" -> prefers-reduced-motion) and ACE is not idle. Idle means
// asleep or muted for more than IDLE_MS; then nothing moves and the webview can rest at ~0 % CPU.

import { useEffect, useState, useSyncExternalStore } from "react";

import type { ConversationState } from "../ipc/generated";

export const IDLE_MS = 5000;
const REDUCED_MOTION = "(prefers-reduced-motion: reduce)";

function subscribeVisibility(onChange: () => void): () => void {
  document.addEventListener("visibilitychange", onChange);
  return () => document.removeEventListener("visibilitychange", onChange);
}

export function usePageVisible(): boolean {
  return useSyncExternalStore(subscribeVisibility, () => document.visibilityState === "visible");
}

function reducedMotionQuery(): MediaQueryList | null {
  return typeof window.matchMedia === "function" ? window.matchMedia(REDUCED_MOTION) : null;
}

function subscribeReducedMotion(onChange: () => void): () => void {
  const query = reducedMotionQuery();
  query?.addEventListener("change", onChange);
  return () => query?.removeEventListener("change", onChange);
}

export function usePrefersReducedMotion(): boolean {
  return useSyncExternalStore(subscribeReducedMotion, () => reducedMotionQuery()?.matches ?? false);
}

/** True once `value` has stayed the same for `ms` milliseconds. */
export function useSettled(value: string | null, ms: number): boolean {
  const [settledValue, setSettledValue] = useState<{ value: string | null } | null>(null);
  useEffect(() => {
    const timer = setTimeout(() => setSettledValue({ value }), ms);
    return () => clearTimeout(timer);
  }, [value, ms]);
  return settledValue !== null && settledValue.value === value;
}

const IDLE_STATES: ReadonlySet<ConversationState | null> = new Set([null, "asleep", "muted"]);

/** Whether the orb (and other ambient motion) should run right now. */
export function useOrbAnimating(state: ConversationState | null): boolean {
  const visible = usePageVisible();
  const reduced = usePrefersReducedMotion();
  const settled = useSettled(state, IDLE_MS);
  return visible && !reduced && !(IDLE_STATES.has(state) && settled);
}
