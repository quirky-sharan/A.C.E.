// The Control Center window (§14.1, §14.5, S05 task 6): header with the orb and live status, the
// shell banner, keyboard-navigable page list, and the selected page. Pages are kept in the URL hash
// (#/dashboard) so a reload stays on the same page.

import { lazy, Suspense, useSyncExternalStore, type KeyboardEvent } from "react";

import { Chip, cx, Orb, ToastViewport, useOrbAnimating } from "../hud";
import { ORB_LOOKS } from "../hud/orb";
import { useConnectionStore, useCoreStore, useSettingsStore, useShellStore } from "../state/stores";
import { Dashboard, StubPage } from "./dashboard";
import { DEFAULT_PAGE, visiblePages, type PageInfo } from "./pages";
import { ConnectionChip, modeLabel, ShellBanner } from "./status-views";

// Development builds only: in release builds this is null and the gallery code is left out.
const Gallery = import.meta.env.DEV
  ? lazy(() => import("./gallery").then((module) => ({ default: module.Gallery })))
  : null;

function subscribeHash(onChange: () => void): () => void {
  window.addEventListener("hashchange", onChange);
  return () => window.removeEventListener("hashchange", onChange);
}

function pageFromHash(pages: readonly PageInfo[]): PageInfo {
  const id = window.location.hash.replace(/^#\/?/, "") || DEFAULT_PAGE;
  return pages.find((page) => page.id === id) ?? pages[0];
}

function openPage(id: string): void {
  window.location.hash = `#/${id}`;
}

function Header() {
  const conversation = useCoreStore((state) => state.state?.conversation ?? null);
  const status = useConnectionStore((state) => state.status);
  const mode = useSettingsStore((state) => state.values["verification.mode"]);
  const animate = useOrbAnimating(conversation);
  return (
    <header className="flex items-center gap-4 border-b border-line px-6 py-4">
      <Orb state={conversation} animate={animate} size={44} />
      <div>
        <h1 className="font-heading text-lg tracking-[0.08em] text-primary">ACE</h1>
        <p className="text-text-dim">
          {conversation ? ORB_LOOKS[conversation].label : "Not connected"}
        </p>
      </div>
      <div className="ml-auto flex items-center gap-2">
        <ConnectionChip status={status} />
        <Chip tone="primary">{modeLabel(mode)}</Chip>
      </div>
    </header>
  );
}

export function ControlCenter({ dev = import.meta.env.DEV }: { dev?: boolean }) {
  const pages = visiblePages(dev);
  const page = useSyncExternalStore(subscribeHash, () => pageFromHash(pages));
  const shell = useShellStore((state) => state.status);

  const onNavKeyDown = (event: KeyboardEvent<HTMLUListElement>) => {
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    event.preventDefault();
    const index = pages.findIndex((entry) => entry.id === page.id);
    const next = pages[(index + (event.key === "ArrowDown" ? 1 : pages.length - 1)) % pages.length];
    openPage(next.id);
    document.getElementById(`nav-${next.id}`)?.focus();
  };

  return (
    <div className="flex h-full">
      <nav
        aria-label="Control Center pages"
        className="w-60 shrink-0 overflow-y-auto border-r border-line bg-panel py-4"
      >
        <ul className="flex flex-col" onKeyDown={onNavKeyDown}>
          {pages.map((entry) => {
            const Icon = entry.icon;
            const current = entry.id === page.id;
            return (
              <li key={entry.id}>
                <button
                  id={`nav-${entry.id}`}
                  type="button"
                  aria-current={current ? "page" : undefined}
                  onClick={() => openPage(entry.id)}
                  className={cx(
                    "flex w-full items-center gap-3 border-l-2 px-4 py-1.5 text-left leading-tight transition-colors duration-150",
                    current
                      ? "border-primary bg-primary/10 text-primary"
                      : "border-transparent text-text-dim hover:text-text",
                  )}
                >
                  <Icon size={16} aria-hidden="true" />
                  <span className="flex-1">{entry.title}</span>
                  {entry.stage && (
                    <span className="font-mono text-[10px] opacity-60">{entry.stage}</span>
                  )}
                </button>
              </li>
            );
          })}
        </ul>
      </nav>
      <div className="flex min-w-0 flex-1 flex-col overflow-y-auto">
        <Header />
        <ShellBanner status={shell} />
        <main className="p-6" aria-label={page.title}>
          {page.id === "dashboard" ? (
            <Dashboard />
          ) : page.id === "gallery" && Gallery ? (
            <Suspense fallback={<p className="text-text-dim">Loading the gallery…</p>}>
              <Gallery />
            </Suspense>
          ) : (
            <StubPage title={page.title} summary={page.summary} stage={page.stage} />
          )}
        </main>
      </div>
      <ToastViewport />
    </div>
  );
}
