// Dashboard (§14.5, S05 task 6): live core state, health, connection and recent tasks (S07);
// quotas and latency are placeholders until their stages.

import { Chip, Panel, StatusDot, StepList } from "../hud";
import { taskLook, toStepView } from "../state/task-views";
import { ORB_LOOKS } from "../hud/orb";
import { useConnectionStore, useCoreStore, useShellStore, useTasksStore } from "../state/stores";
import { HOTKEY_LABELS } from "../shell/status";
import { ConnectionChip, HEALTH_TONES } from "./status-views";

const FLAG_LABELS = {
  game_mode: "Game mode",
  offline: "Offline",
  dnd: "Do not disturb",
  paused_overlay: "Overlay paused",
} as const;

export function Dashboard() {
  const core = useCoreStore((state) => state.state);
  const health = useCoreStore((state) => state.health);
  const connection = useConnectionStore();
  const shell = useShellStore((state) => state.status);
  const tasks = useTasksStore((state) => state.tasks);
  const flags = core
    ? (Object.keys(FLAG_LABELS) as (keyof typeof FLAG_LABELS)[]).filter((flag) => core[flag])
    : [];

  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
      <Panel title="Core" tone="primary">
        {core ? (
          <dl className="grid grid-cols-[8rem_1fr] gap-y-1">
            <dt className="text-text-dim">State</dt>
            <dd>{ORB_LOOKS[core.conversation].label}</dd>
            <dt className="text-text-dim">Flags</dt>
            <dd className="flex flex-wrap gap-1">
              {flags.length === 0 ? (
                <span className="text-text-dim">none</span>
              ) : (
                flags.map((flag) => <Chip key={flag}>{FLAG_LABELS[flag]}</Chip>)
              )}
            </dd>
            <dt className="text-text-dim">Version</dt>
            <dd>
              {connection.coreVersion ?? "—"}
              {connection.dev && " (dev)"}
            </dd>
          </dl>
        ) : (
          <p className="text-text-dim">Waiting for ace-core…</p>
        )}
      </Panel>

      <Panel title="Connection">
        <div className="mb-2 flex items-center gap-3">
          <ConnectionChip status={connection.status} />
          {shell?.core.port != null && (
            <span className="font-mono text-text-dim">port {shell.core.port}</span>
          )}
        </div>
        {connection.detail && <p className="text-text-dim">{connection.detail}</p>}
        {shell && shell.core.restarts > 0 && (
          <p className="text-text-dim">
            The core was restarted {shell.core.restarts}× since ACE started.
          </p>
        )}
      </Panel>

      <Panel title="Health">
        {health ? (
          <ul className="flex flex-col gap-1.5">
            {health.subsystems.map((subsystem) => (
              <li key={subsystem.name} className="flex items-start gap-2">
                <span className="flex h-[21px] shrink-0 items-center">
                  <StatusDot
                    tone={HEALTH_TONES[subsystem.status]}
                    label={`${subsystem.name}: ${subsystem.status}`}
                  />
                </span>
                <span>
                  <span className="font-medium">{subsystem.name}</span>
                  <span className="text-text-dim"> · {subsystem.status}</span>
                  {subsystem.detail && (
                    <span className="block text-text-dim">{subsystem.detail}</span>
                  )}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-text-dim">No health report yet.</p>
        )}
      </Panel>

      <Panel title="Hotkeys">
        {shell && shell.hotkeys.length > 0 ? (
          <ul className="flex flex-col gap-1">
            {shell.hotkeys.map((hotkey) => (
              <li key={hotkey.action} className="flex items-center gap-2">
                <StatusDot
                  tone={
                    hotkey.shortcut === null ? "neutral" : hotkey.registered ? "success" : "danger"
                  }
                  label={
                    hotkey.shortcut === null
                      ? "off"
                      : hotkey.registered
                        ? "registered"
                        : "not registered"
                  }
                />
                <span className="w-44">{HOTKEY_LABELS[hotkey.action]}</span>
                <span className="font-mono text-text-dim">{hotkey.shortcut ?? "off"}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-text-dim">The desktop shell has not reported its hotkeys yet.</p>
        )}
      </Panel>

      <Panel title="Recent tasks">
        {tasks.length === 0 ? (
          <p className="text-text-dim">
            No tasks yet. Type a command in the sidebar (Ctrl+Alt+Shift+Space).
          </p>
        ) : (
          tasks.slice(0, 3).map((task) => (
            <div key={task.id} className="mb-3">
              <p className="mb-1 flex items-center gap-2 font-medium">
                <span className="min-w-0 flex-1 truncate">{task.utterance}</span>
                <Chip tone={taskLook(task).tone}>{taskLook(task).label}</Chip>
              </p>
              <StepList steps={toStepView(task)} />
            </div>
          ))
        )}
      </Panel>

      <Panel title="Quotas & latency">
        <p className="text-text-dim">
          Provider quotas arrive with the provider pool (S15), latency figures with the performance
          pass (S40).
        </p>
      </Panel>
    </div>
  );
}

export function StubPage({
  title,
  summary,
  stage,
}: {
  title: string;
  summary: string;
  stage: string | null;
}) {
  return (
    <Panel title={title}>
      <p className="mb-2">{summary}</p>
      {stage && <p className="text-text-dim">This page arrives in stage {stage}.</p>}
    </Panel>
  );
}
