// Task and decision cards (S05 task 4): StepList with ✓ / ⚠ / ✗ / ↺ badges (§14.3), the
// ConfirmCard for T2 actions (§15.3: the exact action, big Yes / No, 30 s timeout) and the
// ClarifyCard for clarifying questions (§8.1).

import type { StepStatus, TaskStep } from "../state/stores";
import { Button, cx, Panel } from "./primitives";

const BADGES: Record<StepStatus, { glyph: string; label: string; className: string }> = {
  pending: { glyph: "•", label: "pending", className: "text-text-dim" },
  running: { glyph: "…", label: "running", className: "text-primary" },
  done: { glyph: "✓", label: "done", className: "text-success" },
  warning: { glyph: "⚠", label: "warning", className: "text-warning" },
  failed: { glyph: "✗", label: "failed", className: "text-danger" },
  retrying: { glyph: "↺", label: "retrying", className: "text-orange" },
};

export function StepList({ steps }: { steps: TaskStep[] }) {
  return (
    <ol className="flex flex-col gap-1.5">
      {steps.map((step) => {
        const badge = BADGES[step.status];
        return (
          <li key={step.id} data-status={step.status} className="flex items-center gap-2">
            <span
              role="img"
              aria-label={badge.label}
              className={cx("w-4 text-center font-mono", badge.className)}
            >
              {badge.glyph}
            </span>
            <span className={step.status === "pending" ? "text-text-dim" : undefined}>
              {step.label}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

export interface ConfirmCardProps {
  /** The exact action, e.g. "Send to Mom on WhatsApp: 'I'll be home by 8'". */
  action: string;
  secondsLeft?: number | null;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmCard({
  action,
  secondsLeft,
  busy = false,
  onConfirm,
  onCancel,
}: ConfirmCardProps) {
  return (
    <Panel title="Confirm" tone="orange">
      <p className="mb-3 text-base">{action}</p>
      {secondsLeft != null && (
        <p className="mb-3 text-xs text-text-dim" aria-live="polite">
          Cancels by itself in {secondsLeft} s
        </p>
      )}
      <div className="flex gap-3">
        <Button variant="primary" size="lg" disabled={busy} onClick={onConfirm}>
          Yes
        </Button>
        <Button size="lg" disabled={busy} onClick={onCancel}>
          No
        </Button>
      </div>
    </Panel>
  );
}

export interface ClarifyOption {
  id: string;
  label: string;
}

export interface ClarifyCardProps {
  question: string;
  options: ClarifyOption[];
  onChoose: (id: string) => void;
  onCancel?: () => void;
}

export function ClarifyCard({ question, options, onChoose, onCancel }: ClarifyCardProps) {
  return (
    <Panel title="Which one?" tone="orange">
      <p className="mb-3 text-base">{question}</p>
      <div className="flex flex-wrap gap-2">
        {options.map((option) => (
          <Button key={option.id} variant="primary" onClick={() => onChoose(option.id)}>
            {option.label}
          </Button>
        ))}
        {onCancel && <Button onClick={onCancel}>Cancel</Button>}
      </div>
    </Panel>
  );
}
