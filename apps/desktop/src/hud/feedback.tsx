// Toasts and the text input (S05 task 4, §14.3). Toasts enter and leave with Motion (150–250 ms,
// skipped for reduced motion); the input sends on Enter, clears on Esc and recalls history with ↑ / ↓.

import { X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useState, type KeyboardEvent, type ReactNode } from "react";

import { useNotificationsStore, type Tone as NotificationTone } from "../state/stores";
import { cx } from "./primitives";

const TOAST_TONES: Record<NotificationTone, string> = {
  info: "border-primary/60",
  success: "border-success/70",
  warning: "border-warning/70",
  danger: "border-danger/70",
};

export interface ToastAction {
  label: string;
  onClick: () => void;
}

export interface ToastProps {
  tone: NotificationTone;
  title: string;
  message?: string;
  actions?: ToastAction[];
  onDismiss?: () => void;
}

export function Toast({ tone, title, message, actions, onDismiss }: ToastProps) {
  return (
    <div
      role="status"
      data-tone={tone}
      className={cx(
        "hud-corners w-80 rounded-sm border bg-panel px-4 py-3 shadow-glow",
        TOAST_TONES[tone],
      )}
    >
      <div className="flex items-start gap-3">
        <div className="flex-1">
          <p className="font-medium">{title}</p>
          {message && <p className="text-text-dim">{message}</p>}
        </div>
        {onDismiss && (
          <button
            type="button"
            aria-label="Dismiss"
            onClick={onDismiss}
            className="text-text-dim hover:text-text"
          >
            <X size={16} aria-hidden="true" />
          </button>
        )}
      </div>
      {actions && actions.length > 0 && (
        <div className="mt-2 flex gap-3">
          {actions.map((action) => (
            <button
              key={action.label}
              type="button"
              onClick={action.onClick}
              className="text-sm text-primary hover:underline"
            >
              {action.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export const TOAST_MS = 6000;

function TimedToast({ id, children }: { id: number; children: ReactNode }) {
  const dismiss = useNotificationsStore((state) => state.dismiss);
  useEffect(() => {
    const timer = setTimeout(() => dismiss(id), TOAST_MS);
    return () => clearTimeout(timer);
  }, [dismiss, id]);
  return <>{children}</>;
}

/** The corner where the notifications store's toasts appear. */
export function ToastViewport() {
  const items = useNotificationsStore((state) => state.items);
  const dismiss = useNotificationsStore((state) => state.dismiss);
  return (
    <div
      aria-live="polite"
      className="pointer-events-none fixed right-4 bottom-4 flex flex-col gap-2"
    >
      <AnimatePresence initial={false}>
        {items.map((item) => (
          <motion.div
            key={item.id}
            className="pointer-events-auto"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 12 }}
            transition={{ duration: 0.2, ease: "easeOut" }}
          >
            <TimedToast id={item.id}>
              <Toast
                tone={item.tone}
                title={item.title}
                message={item.message}
                onDismiss={() => dismiss(item.id)}
              />
            </TimedToast>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}

export interface TextInputProps {
  label: string;
  onSubmit: (text: string) => void;
  /** Earlier entries, oldest first; ↑ walks back through them. */
  history?: string[];
  placeholder?: string;
  disabled?: boolean;
  onEscape?: () => void;
}

export function TextInput({
  label,
  onSubmit,
  history = [],
  placeholder,
  disabled,
  onEscape,
}: TextInputProps) {
  const [value, setValue] = useState("");
  const [cursor, setCursor] = useState<number | null>(null);

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") {
      const text = value.trim();
      if (text) {
        onSubmit(text);
        setValue("");
        setCursor(null);
      }
    } else if (event.key === "Escape") {
      setValue("");
      setCursor(null);
      onEscape?.();
    } else if (event.key === "ArrowUp" && history.length > 0) {
      event.preventDefault();
      const next = cursor === null ? history.length - 1 : Math.max(cursor - 1, 0);
      setCursor(next);
      setValue(history[next]);
    } else if (event.key === "ArrowDown" && cursor !== null) {
      event.preventDefault();
      const next = cursor + 1;
      if (next >= history.length) {
        setCursor(null);
        setValue("");
      } else {
        setCursor(next);
        setValue(history[next]);
      }
    }
  };

  return (
    <input
      type="text"
      aria-label={label}
      value={value}
      placeholder={placeholder}
      disabled={disabled}
      onChange={(event) => {
        setValue(event.target.value);
        setCursor(null);
      }}
      onKeyDown={onKeyDown}
      className={cx(
        "w-full rounded-sm border border-line bg-bg px-3 py-2 text-text placeholder:text-text-dim",
        "focus:border-primary focus:shadow-glow focus:outline-none disabled:opacity-40",
      )}
    />
  );
}
