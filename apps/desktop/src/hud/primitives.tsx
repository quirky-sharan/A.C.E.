// Basic HUD building blocks (S05 task 4): Panel, Button, Toggle, Chip. JARVIS look per §14.4:
// dark panels, 1 px glowing lines, corner brackets, Orbitron headings in capitals.

import * as Switch from "@radix-ui/react-switch";
import { useId, type ButtonHTMLAttributes, type ReactNode } from "react";

export function cx(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(" ");
}

export type Tone = "neutral" | "primary" | "success" | "warning" | "danger" | "violet" | "orange";

const BORDER_BY_TONE: Record<Tone, string> = {
  neutral: "border-line",
  primary: "border-primary/60",
  success: "border-success/70",
  warning: "border-warning/70",
  danger: "border-danger/70",
  violet: "border-violet/70",
  orange: "border-orange/70",
};

const TEXT_BY_TONE: Record<Tone, string> = {
  neutral: "text-text-dim",
  primary: "text-primary",
  success: "text-success",
  warning: "text-warning",
  danger: "text-danger",
  violet: "text-violet",
  orange: "text-orange",
};

export function Heading({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <h2 className={cx("font-heading text-xs uppercase tracking-[0.08em] text-primary", className)}>
      {children}
    </h2>
  );
}

export interface PanelProps {
  title?: string;
  tone?: Tone;
  actions?: ReactNode;
  className?: string;
  children: ReactNode;
}

export function Panel({ title, tone = "neutral", actions, className, children }: PanelProps) {
  return (
    <section
      aria-label={title}
      data-tone={tone}
      className={cx("hud-corners rounded-sm border bg-panel p-4", BORDER_BY_TONE[tone], className)}
    >
      {(title || actions) && (
        <header className="mb-3 flex items-center justify-between gap-3">
          {title && <Heading>{title}</Heading>}
          {actions}
        </header>
      )}
      {children}
    </section>
  );
}

export type ButtonVariant = "primary" | "ghost" | "danger";

const BUTTON_VARIANTS: Record<ButtonVariant, string> = {
  primary: "border-primary bg-primary/15 text-primary hover:bg-primary/25 hover:shadow-glow",
  ghost: "border-line text-text hover:border-primary/60 hover:text-primary",
  danger: "border-danger/70 bg-danger/10 text-danger hover:bg-danger/20",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: "sm" | "md" | "lg";
}

const BUTTON_SIZES = {
  sm: "px-2 py-1 text-xs",
  md: "px-3 py-1.5 text-sm",
  lg: "px-5 py-2.5 text-base",
};

export function Button({ variant = "ghost", size = "md", className, ...props }: ButtonProps) {
  return (
    <button
      type="button"
      data-variant={variant}
      className={cx(
        "rounded-sm border font-medium transition-[background-color,border-color,color,box-shadow] duration-200 ease-hud",
        "disabled:cursor-not-allowed disabled:opacity-40",
        BUTTON_VARIANTS[variant],
        BUTTON_SIZES[size],
        className,
      )}
      {...props}
    />
  );
}

export interface ToggleProps {
  label: string;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  disabled?: boolean;
}

/** An accessible on / off switch (Radix Switch: role="switch", Space / Enter toggle). */
export function Toggle({ label, checked, onCheckedChange, disabled }: ToggleProps) {
  const id = useId();
  return (
    <div className="flex items-center gap-3">
      <Switch.Root
        id={id}
        checked={checked}
        onCheckedChange={onCheckedChange}
        disabled={disabled}
        className={cx(
          "relative h-5 w-9 shrink-0 rounded-full border border-line bg-bg transition-colors duration-200",
          "data-[state=checked]:border-primary data-[state=checked]:bg-primary/25",
          "disabled:cursor-not-allowed disabled:opacity-40",
        )}
      >
        <Switch.Thumb
          className={cx(
            "block h-3.5 w-3.5 translate-x-0.5 rounded-full bg-text-dim transition-transform duration-200",
            "data-[state=checked]:translate-x-[18px] data-[state=checked]:bg-primary",
          )}
        />
      </Switch.Root>
      <label htmlFor={id} className={cx("select-none", disabled && "opacity-40")}>
        {label}
      </label>
    </div>
  );
}

export function Chip({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span
      data-tone={tone}
      className={cx(
        "inline-flex items-center gap-1 rounded-sm border px-2 py-0.5",
        "font-heading text-[10px] uppercase tracking-[0.08em]",
        BORDER_BY_TONE[tone],
        TEXT_BY_TONE[tone],
      )}
    >
      {children}
    </span>
  );
}

const DOT_BY_TONE: Record<Tone, string> = {
  neutral: "bg-text-dim",
  primary: "bg-primary",
  success: "bg-success",
  warning: "bg-warning",
  danger: "bg-danger",
  violet: "bg-violet",
  orange: "bg-orange",
};

/** A small status light with an accessible name. */
export function StatusDot({ tone, label }: { tone: Tone; label: string }) {
  return (
    <span
      role="img"
      aria-label={label}
      title={label}
      data-tone={tone}
      className={cx("inline-block h-2 w-2 rounded-full", DOT_BY_TONE[tone])}
    />
  );
}
