// Skills & Permissions (§14.5). S08 adds the app index (S08 task 6): every app ACE can open, read
// from the Start menu, with how often ACE opened it. Search and refresh go through the core.

import { useEffect, useState } from "react";

import { Button, Chip, Panel } from "../hud";
import type { IpcClient } from "../ipc/client";
import type { AppInfo } from "../ipc/generated";

export const LIST_DELAY_MS = 200;
const LIMIT = 500;

const KIND_LABELS: Record<string, string> = {
  aumid: "Store app",
  exe: "Desktop app",
  other: "Shortcut",
};

function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export function Skills({ client }: { client: IpcClient | null }) {
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<{ available: boolean; apps: AppInfo[] } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    if (client === null) return;
    let current = true;
    const text = query.trim();
    const timer = window.setTimeout(() => {
      client
        .request("apps.list", { query: text === "" ? null : text, limit: LIMIT })
        .then((answer) => {
          if (!current) return;
          setResult(answer);
          setError(null);
        })
        .catch((reason: unknown) => {
          if (current) setError(message(reason));
        });
    }, LIST_DELAY_MS);
    return () => {
      current = false;
      window.clearTimeout(timer);
    };
  }, [client, query, version]);

  const refresh = () => {
    if (client === null) return;
    setRefreshing(true);
    client
      .request("apps.refresh", {})
      .then(() => setVersion((n) => n + 1))
      .catch((reason: unknown) => setError(message(reason)))
      .finally(() => setRefreshing(false));
  };

  const apps = result?.apps ?? [];
  return (
    <div className="flex flex-col gap-4">
      <Panel
        title="App index"
        actions={
          <Button size="sm" disabled={client === null || refreshing} onClick={refresh}>
            {refreshing ? "Refreshing…" : "Refresh from Start"}
          </Button>
        }
      >
        <p className="mb-3 text-text-dim">
          The apps ACE can open by name ("open spotify"), read from the Start menu at start-up and
          once a day. Apps you open more often win close matches.
        </p>
        <label className="mb-3 flex max-w-xl flex-col gap-1">
          <span className="text-text-dim">Search apps</span>
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="e.g. spotify, code, python"
            className="rounded-sm border border-line bg-bg px-3 py-2 text-text placeholder:text-text-dim focus:border-primary focus:outline-none"
          />
        </label>
        {error && <p className="mb-2 text-danger">Couldn't load the apps: {error}</p>}
        {result !== null && !result.available ? (
          <p className="text-text-dim">App control is not available on this system.</p>
        ) : result === null ? (
          <p className="text-text-dim">Loading…</p>
        ) : apps.length === 0 ? (
          <p className="text-text-dim">No apps match.</p>
        ) : (
          <ul aria-label="Apps" className="flex flex-col divide-y divide-line">
            {apps.map((app) => (
              <li key={app.target} className="flex items-center gap-3 py-1.5">
                <span className="min-w-0 flex-1 truncate">{app.name}</span>
                <Chip tone={app.kind === "aumid" ? "violet" : "neutral"}>
                  {KIND_LABELS[app.kind] ?? app.kind}
                </Chip>
                <span className="w-24 text-right text-xs text-text-dim">
                  {app.launch_count === 0 ? "never opened" : `opened ${app.launch_count}×`}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Panel>
      <p className="text-xs text-text-dim">
        Turning skills on or off, the tier view and pre-approvals arrive in later stages.
      </p>
    </div>
  );
}
