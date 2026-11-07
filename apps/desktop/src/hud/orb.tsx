// The orb (§5.4 visuals, §14.4): thin SVG rings around a core, coloured by ACE's conversation state.
// Motion comes from CSS keyframes that run only while `animate` is true (see activity.ts).

import type { ConversationState } from "../ipc/generated";

export type OrbMotion =
  "breathe" | "pulse" | "spin" | "progress" | "shimmer" | "outline" | "flash" | "none";

export interface OrbLook {
  label: string;
  color: string;
  motion: OrbMotion;
  dim?: boolean;
  outline?: boolean;
  slash?: boolean;
}

export const ORB_LOOKS: Record<ConversationState, OrbLook> = {
  asleep: { label: "Asleep", color: "var(--color-primary)", motion: "breathe", dim: true },
  listening: { label: "Listening", color: "var(--color-primary)", motion: "pulse" },
  transcribing: { label: "Transcribing", color: "var(--color-violet)", motion: "shimmer" },
  thinking: { label: "Thinking", color: "var(--color-violet)", motion: "spin" },
  acting: { label: "Acting", color: "var(--color-warning)", motion: "progress" },
  speaking: { label: "Speaking", color: "var(--color-primary)", motion: "pulse" },
  awaiting_confirm: { label: "Waiting for your OK", color: "var(--color-orange)", motion: "pulse" },
  awaiting_answer: {
    label: "Waiting for your answer",
    color: "var(--color-orange)",
    motion: "pulse",
  },
  follow_up: {
    label: "Listening for a follow-up",
    color: "var(--color-primary)",
    motion: "outline",
    outline: true,
  },
  dictating: { label: "Dictating", color: "var(--color-success)", motion: "none", outline: true },
  muted: { label: "Microphone muted", color: "var(--color-text-dim)", motion: "none", slash: true },
  error: { label: "Something went wrong", color: "var(--color-danger)", motion: "flash" },
};

/** Shown while the core is not connected. */
const OFFLINE_LOOK: OrbLook = {
  label: "Not connected",
  color: "var(--color-line)",
  motion: "none",
  dim: true,
};

export interface OrbProps {
  state: ConversationState | null;
  animate: boolean;
  size?: number;
  /** ACTING progress from 0 to 1 (draws the amber progress ring). */
  progress?: number;
}

const RING = 40;
const CIRCUMFERENCE = 2 * Math.PI * RING;

export function Orb({ state, animate, size = 56, progress }: OrbProps) {
  const look = state === null ? OFFLINE_LOOK : ORB_LOOKS[state];
  const shown = Math.min(Math.max(progress ?? 0, 0), 1);
  return (
    <svg
      className="orb shrink-0 drop-shadow-[0_0_6px_currentColor]"
      data-state={state ?? "offline"}
      data-motion={look.motion}
      data-animate={animate && look.motion !== "none" ? "true" : "false"}
      viewBox="0 0 100 100"
      width={size}
      height={size}
      role="img"
      aria-label={`ACE: ${look.label}`}
      style={{ color: look.color }}
    >
      <circle
        className="orb-outline"
        cx="50"
        cy="50"
        r="47"
        fill="none"
        stroke="currentColor"
        strokeWidth={look.outline ? 2 : 1}
        opacity={look.outline ? 0.9 : 0.3}
      />
      <g className="orb-spin">
        <circle
          cx="50"
          cy="50"
          r={RING}
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeDasharray="20 9"
          opacity="0.75"
        />
      </g>
      {state === "acting" && (
        <circle
          className="orb-progress"
          cx="50"
          cy="50"
          r={RING}
          fill="none"
          stroke="currentColor"
          strokeWidth="4"
          strokeDasharray={`${CIRCUMFERENCE * shown} ${CIRCUMFERENCE}`}
          transform="rotate(-90 50 50)"
        />
      )}
      <circle
        className="orb-core"
        cx="50"
        cy="50"
        r="22"
        fill="currentColor"
        opacity={look.dim ? 0.5 : 0.85}
      />
      {look.slash && (
        <line
          className="orb-slash"
          x1="30"
          y1="70"
          x2="70"
          y2="30"
          strokeWidth="6"
          strokeLinecap="round"
          style={{ stroke: "var(--color-bg)" }}
        />
      )}
    </svg>
  );
}
