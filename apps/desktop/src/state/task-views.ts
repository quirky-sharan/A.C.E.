// How tasks look in the UI (§14.3): step badges, status labels and tones, confirmation countdowns.

import type { Tone } from "../hud/primitives";
import type { StepStatus as CoreStepStatus, TaskInfo, TaskStatus } from "../ipc/generated";
import type { StepStatus, TaskStep } from "./stores";

/** The Supervisor's code for a forbidden (T3) action: shown as "Refused", not "Failed". */
export const REFUSED_CODE = "E_SUPERVISOR_FORBIDDEN";

const STEP_LOOK: Record<CoreStepStatus, StepStatus> = {
  pending: "pending",
  running: "running",
  waiting_user: "pending",
  succeeded: "done",
  failed: "failed",
  cancelled: "warning",
  refused: "failed",
};

export interface TaskLook {
  label: string;
  tone: Tone;
  glyph: string;
}

const TASK_LOOK: Record<TaskStatus, TaskLook> = {
  queued: { label: "Queued", tone: "neutral", glyph: "•" },
  running: { label: "Running", tone: "primary", glyph: "…" },
  waiting_user: { label: "Waiting for you", tone: "orange", glyph: "?" },
  verifying: { label: "Checking", tone: "violet", glyph: "…" },
  succeeded: { label: "Done", tone: "success", glyph: "✓" },
  failed: { label: "Failed", tone: "danger", glyph: "✗" },
  cancelled: { label: "Cancelled", tone: "warning", glyph: "⚠" },
  interrupted: { label: "Interrupted", tone: "warning", glyph: "⚠" },
};

export function toStepView(task: TaskInfo): TaskStep[] {
  return task.steps.map((step) => ({
    id: step.id,
    label: step.label,
    status: STEP_LOOK[step.status],
  }));
}

export function taskLook(task: TaskInfo): TaskLook {
  if (task.error_code === REFUSED_CODE) return { label: "Refused", tone: "danger", glyph: "✗" };
  return TASK_LOOK[task.status];
}

export function isActive(task: TaskInfo): boolean {
  return task.finished_at === null;
}

/** Whole seconds until `expiresAt` (never negative). */
export function secondsLeft(expiresAt: string, now: number = Date.now()): number {
  return Math.max(0, Math.ceil((Date.parse(expiresAt) - now) / 1000));
}

export function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}
