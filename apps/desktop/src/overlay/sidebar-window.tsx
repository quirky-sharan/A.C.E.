// The slide-out sidebar (§14.3, S06): header, transcript, current task, background jobs, the
// confirmation / clarification area, the text input and footer toggles. Sections whose backends
// arrive later show what will appear there and when. While closed, the shell hides the window
// (once the panel has slid out); while open, everything outside the panel lets clicks through.

import { listen } from "@tauri-apps/api/event";
import { X } from "lucide-react";
import { motion } from "motion/react";
import { useEffect, useRef, useState } from "react";

import { modeLabel } from "../control-center/status-views";
import {
  Button,
  Chip,
  Heading,
  Orb,
  StatusDot,
  StepList,
  TextInput,
  useOrbAnimating,
  type Tone,
} from "../hud";
import { ORB_LOOKS } from "../hud/orb";
import { useConnectionStore, useCoreStore, useSettingsStore, useTasksStore } from "../state/stores";
import {
  closeSidebar,
  focusSidebarInput,
  getOverlayState,
  hideOverlayFor,
  overlayInput,
  reportSummonFocus,
  sidebarHidden,
  SIDEBAR_EVENT,
  type Edge,
  type SidebarEvent,
} from "./overlay-api";
import { useHitRects } from "./use-hit-rects";

const SLIDE_PX = 420;
const HIDE_MINUTES = 60;

function HealthDots() {
  const status = useConnectionStore((state) => state.status);
  const offline = useCoreStore((state) => state.state?.offline ?? false);
  const internet: [Tone, string] =
    status !== "connected"
      ? ["neutral", "internet: unknown"]
      : offline
        ? ["danger", "internet: offline"]
        : ["success", "internet: ok"];
  const later: [Tone, string][] = [
    ["neutral", "providers: arrive in S15"],
    ["neutral", "Chrome bridge: arrives in S24"],
    ["neutral", "microphone: arrives in S09"],
  ];
  return (
    <span className="flex items-center gap-1.5">
      {[internet, ...later].map(([tone, label]) => (
        <StatusDot key={label} tone={tone} label={label} />
      ))}
    </span>
  );
}

export function SidebarWindow({ initialOpen = false }: { initialOpen?: boolean }) {
  const [open, setOpen] = useState(initialOpen);
  const [shown, setShown] = useState(initialOpen); // drawn: open, or still sliding out
  const [focusRequests, setFocusRequests] = useState(0);
  const focusHandled = useRef(0);
  const [edge, setEdge] = useState<Edge>("right");
  const [history, setHistory] = useState<string[]>([]);
  const [note, setNote] = useState<string | null>(null);
  const panel = useRef<HTMLElement>(null);
  const conversation = useCoreStore((state) => state.state?.conversation ?? null);
  const mode = useSettingsStore((state) => state.values["verification.mode"]);
  const task = useTasksStore(
    (state) => state.tasks.find((entry) => entry.status === "running") ?? null,
  );
  const animate = useOrbAnimating(conversation);
  useHitRects([panel], open && shown);

  useEffect(() => {
    let active = true;
    let eventSeen = false;
    const stop = listen<SidebarEvent>(SIDEBAR_EVENT, ({ payload }) => {
      eventSeen = true;
      if (!active) return;
      setEdge(payload.edge);
      setOpen(payload.open);
      if (payload.open) setShown(true);
      if (payload.open && payload.focus) setFocusRequests((count) => count + 1);
    }).catch(() => () => {});
    getOverlayState()
      .then((view) => {
        if (!active || eventSeen) return; // an event is newer
        setEdge(view.edge);
        setOpen(view.sidebarOpen);
        setShown(view.sidebarOpen);
      })
      .catch(() => {});
    return () => {
      active = false;
      void stop.then((unlisten) => unlisten());
    };
  }, []);

  // Summoned: focus the input once the panel is drawn, then report the time (NFR-1).
  useEffect(() => {
    if (!shown || focusRequests === focusHandled.current) return;
    focusHandled.current = focusRequests;
    panel.current?.querySelector("input")?.focus();
    void reportSummonFocus().catch(() => {});
  }, [shown, focusRequests]);

  const requestClose = () => {
    setOpen(false); // slides out; onAnimationComplete then lets the shell hide the window
    void closeSidebar().catch(() => {}); // the shell gives the focus back right away
  };

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") requestClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const offscreen = edge === "right" ? SLIDE_PX : -SLIDE_PX;

  return (
    <div className="flex h-full w-full p-2">
      {shown && (
        <motion.aside
          ref={panel}
          aria-label="ACE sidebar"
          initial={{ x: offscreen }}
          animate={{ x: open ? 0 : offscreen }}
          transition={{ duration: 0.2, ease: "easeOut" }}
          onAnimationComplete={() => {
            if (open) return;
            setShown(false);
            void sidebarHidden().catch(() => {});
          }}
          className="hud-corners flex h-full w-full flex-col gap-3 rounded-sm border border-primary/40 bg-panel/95 p-4 shadow-glow"
        >
          <header className="flex items-center gap-3">
            <Orb state={conversation} animate={animate} size={32} />
            <div className="min-w-0 flex-1">
              <p className="font-heading text-sm tracking-[0.08em] text-primary">ACE</p>
              <p className="truncate text-xs text-text-dim">
                {conversation ? ORB_LOOKS[conversation].label : "Not connected"}
              </p>
            </div>
            <Chip tone="primary">{modeLabel(mode)}</Chip>
            <HealthDots />
            <button
              type="button"
              aria-label="Close the sidebar"
              onClick={requestClose}
              className="text-text-dim hover:text-text"
            >
              <X size={16} aria-hidden="true" />
            </button>
          </header>

          <section aria-label="Conversation" className="min-h-0 flex-1 overflow-y-auto">
            <Heading className="mb-1">Conversation</Heading>
            <p className="text-text-dim">
              Nothing yet. Typed commands arrive in stage S07, voice in S13.
            </p>
          </section>

          <section aria-label="Current task">
            <Heading className="mb-1">Current task</Heading>
            {task ? (
              <>
                <p className="mb-1 font-medium">{task.title}</p>
                <StepList steps={task.steps} />
                <div className="mt-2 flex gap-2">
                  <Button size="sm" disabled>
                    Show me
                  </Button>
                  <Button size="sm" variant="danger" disabled>
                    Stop
                  </Button>
                </div>
              </>
            ) : (
              <p className="text-text-dim">No task running.</p>
            )}
          </section>

          <section aria-label="Background jobs">
            <Heading className="mb-1">Background jobs</Heading>
            <p className="text-text-dim">None. Background tasks arrive in stage S17.</p>
          </section>

          <div
            onPointerDownCapture={() => {
              void focusSidebarInput().catch(() => {});
            }}
          >
            <TextInput
              label="Command"
              placeholder="Type a command — Enter sends, Esc closes"
              history={history}
              onEscape={requestClose}
              onSubmit={(text) => {
                setHistory((entries) => [...entries.slice(-49), text]);
                setNote("Typed commands arrive in stage S07; this one was not sent.");
              }}
            />
            {note && <p className="mt-1 text-xs text-text-dim">{note}</p>}
          </div>

          <footer className="flex flex-wrap items-center gap-2 border-t border-line pt-3">
            <Button size="sm" onClick={() => void overlayInput("mic_mute").catch(() => {})}>
              Mute mic
            </Button>
            <Button size="sm" disabled title="Do not disturb arrives in stage S37">
              Do not disturb
            </Button>
            <Button
              size="sm"
              className="ml-auto"
              onClick={() => void hideOverlayFor(HIDE_MINUTES).catch(() => {})}
            >
              Hide for 1 hour
            </Button>
          </footer>
        </motion.aside>
      )}
    </div>
  );
}
