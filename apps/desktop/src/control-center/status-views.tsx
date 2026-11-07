// Small views of live status used by the header and the Dashboard.

import type { ConnectionStatus } from "../ipc/client";
import type { HealthStatus } from "../ipc/generated";
import { Chip, cx, type Tone } from "../hud";
import { bannerFor, hotkeyNotices, type ShellStatus } from "../shell/status";

const CONNECTION_LOOKS: Record<ConnectionStatus, { tone: Tone; label: string }> = {
  idle: { tone: "neutral", label: "Not connected" },
  connecting: { tone: "warning", label: "Connecting…" },
  connected: { tone: "success", label: "Connected" },
  reconnecting: { tone: "warning", label: "Reconnecting…" },
  stopped: { tone: "danger", label: "Disconnected" },
};

export function ConnectionChip({ status }: { status: ConnectionStatus }) {
  const look = CONNECTION_LOOKS[status];
  return <Chip tone={look.tone}>{look.label}</Chip>;
}

export const HEALTH_TONES: Record<HealthStatus, Tone> = {
  ok: "success",
  degraded: "warning",
  down: "danger",
};

const MODE_LABELS: Record<string, string> = {
  fast: "Fast",
  balanced: "Balanced",
  paranoid: "Paranoid",
};

/** The verification mode setting (D-09) as a label; Balanced when unset or unknown. */
export function modeLabel(value: unknown): string {
  return (typeof value === "string" && MODE_LABELS[value]) || "Balanced";
}

const BANNER_TONES = {
  info: "border-primary/60",
  warning: "border-warning/70",
  danger: "border-danger/70",
};

/** The desktop shell's banner (S04): core starting / restarting / stopped / safe mode, hotkey problems. */
export function ShellBanner({ status }: { status: ShellStatus | null }) {
  if (status === null) return null;
  const banner = bannerFor(status.core);
  const notices = hotkeyNotices(status.hotkeys);
  if (banner === null && notices.length === 0) return null;
  return (
    <div className="flex flex-col gap-2 px-6 pt-4">
      {banner && (
        <div
          role="status"
          data-tone={banner.tone}
          className={cx("rounded-sm border bg-panel px-4 py-2", BANNER_TONES[banner.tone])}
        >
          <p className="font-medium">{banner.title}</p>
          {banner.detail && <p className="text-text-dim">{banner.detail}</p>}
        </div>
      )}
      {notices.length > 0 && (
        <div
          role="alert"
          className={cx("rounded-sm border bg-panel px-4 py-2", BANNER_TONES.warning)}
        >
          <p className="font-medium">Some hotkeys are not available</p>
          {notices.map((notice) => (
            <p key={notice} className="text-text-dim">
              {notice}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}
