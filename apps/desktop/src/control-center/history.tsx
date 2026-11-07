// History (§14.5, S07): tasks newest first with their steps, tiers and replies. Without a search
// it shows the window's live task list; a search asks the core (utterance, intent or reply).
// Verification details join when the council arrives (S18).

import { useEffect, useState } from "react";

import { Chip, Panel, StepList } from "../hud";
import type { IpcClient } from "../ipc/client";
import type { TaskInfo } from "../ipc/generated";
import { useTasksStore } from "../state/stores";
import { formatTime, taskLook, toStepView } from "../state/task-views";

export const SEARCH_DELAY_MS = 250;
const SEARCH_LIMIT = 100;

function TaskRow({ task }: { task: TaskInfo }) {
  const look = taskLook(task);
  return (
    <li>
      <Panel title={task.utterance} actions={<Chip tone={look.tone}>{look.label}</Chip>}>
        <p className="mb-2 text-xs text-text-dim">
          {formatTime(task.created_at)} · <span className="font-mono">{task.intent}</span> ·{" "}
          {task.mode} mode
        </p>
        {task.result_summary && <p className="mb-2">{task.result_summary}</p>}
        <StepList steps={toStepView(task)} />
        <p className="mt-2 flex flex-wrap items-center gap-2 text-xs text-text-dim">
          {task.steps.map((step) => (
            <span key={step.id} className="flex items-center gap-1">
              <span className="font-mono">{step.skill_id}</span>
              <Chip
                tone={step.tier === "T3" ? "danger" : step.tier === "T2" ? "orange" : "neutral"}
              >
                {step.tier}
              </Chip>
            </span>
          ))}
          {task.error_code && <span className="font-mono text-danger">{task.error_code}</span>}
        </p>
      </Panel>
    </li>
  );
}

export function History({ client }: { client: IpcClient | null }) {
  const live = useTasksStore((state) => state.tasks);
  const [query, setQuery] = useState("");
  // Each answer remembers its query, so a stale answer is simply not shown.
  const [found, setFound] = useState<{ query: string; tasks: TaskInfo[] } | null>(null);
  const [failure, setFailure] = useState<{ query: string; message: string } | null>(null);
  const text = query.trim();
  const searching = text !== "" && client !== null;

  useEffect(() => {
    if (text === "" || client === null) return;
    let current = true;
    const timer = window.setTimeout(() => {
      client
        .request("task.list", { limit: SEARCH_LIMIT, query: text })
        .then((result) => {
          if (current) setFound({ query: text, tasks: result.tasks });
        })
        .catch((reason: unknown) => {
          const message = reason instanceof Error ? reason.message : String(reason);
          if (current) setFailure({ query: text, message });
        });
    }, SEARCH_DELAY_MS);
    return () => {
      current = false;
      window.clearTimeout(timer);
    };
  }, [client, text]);

  const results = searching && found?.query === text ? found.tasks : null;
  const error = searching && failure?.query === text ? failure.message : null;
  const tasks = searching ? (results ?? []) : live;
  return (
    <div className="flex flex-col gap-4">
      <label className="flex max-w-xl flex-col gap-1">
        <span className="text-text-dim">Search tasks</span>
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="e.g. spotify, echo, refused"
          className="rounded-sm border border-line bg-bg px-3 py-2 text-text placeholder:text-text-dim focus:border-primary focus:outline-none"
        />
      </label>
      {error && <p className="text-danger">Search failed: {error}</p>}
      {tasks.length === 0 ? (
        <p className="text-text-dim">
          {!searching
            ? "No tasks yet. Type a command in the sidebar (Ctrl+Alt+Shift+Space)."
            : results !== null
              ? "No tasks match."
              : error === null
                ? "Searching…"
                : null}
        </p>
      ) : (
        <ol aria-label="Tasks" className="flex flex-col gap-3">
          {tasks.map((task) => (
            <TaskRow key={task.id} task={task} />
          ))}
        </ol>
      )}
      <p className="text-xs text-text-dim">
        Verification details for each step arrive with the verification council (S18).
      </p>
    </div>
  );
}
