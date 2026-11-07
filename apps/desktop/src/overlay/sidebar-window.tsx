// The slide-out sidebar (§14.3, S06; live since S07): header, conversation, current task,
// background jobs, confirmation cards, the text input and footer toggles. Typed commands go to
// the core's command pipeline (FR-IN-3). While closed, the shell hides the window (once the panel
// has slid out); while open, everything outside the panel lets clicks through.

import { listen } from "@tauri-apps/api/event";
import { X } from "lucide-react";
import { motion } from "motion/react";
import { useEffect, useRef, useState } from "react";

import { modeLabel } from "../control-center/status-views";
import {
  Button,
  Chip,
  ConfirmCard,
  cx,
  Heading,
  Orb,
  StatusDot,
  StepList,
  TextInput,
  useOrbAnimating,
  type Tone,
} from "../hud";
import { ORB_LOOKS } from "../hud/orb";
import type { IpcClient } from "../ipc/client";
import type { ConfirmationInfo, MessageInfo, TaskInfo } from "../ipc/generated";
import { answerConfirmation, cancelTask, submitCommand } from "../state/core-link";
import {
  useConnectionStore,
  useCoreStore,
  useMessagesStore,
  useSettingsStore,
  useTasksStore,
} from "../state/stores";
import { isActive, secondsLeft, taskLook, toStepView } from "../state/task-views";
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
const SHOWN_MESSAGES = 60;

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

function MessageRow({ message, task }: { message: MessageInfo; task: TaskInfo | undefined }) {
  const fromUser = message.role === "user";
  const look = task && !isActive(task) ? taskLook(task) : null;
  return (
    <li className={cx("flex flex-col", fromUser ? "items-end" : "items-start")}>
      <p
        className={cx(
          "max-w-[85%] rounded-sm px-2 py-1",
          fromUser ? "bg-primary/10 text-text" : "border border-line bg-bg/60",
        )}
      >
        {look && (
          <span role="img" aria-label={look.label} className="mr-1.5 font-mono">
            {look.glyph}
          </span>
        )}
        {message.text}
      </p>
      {message.detail && (
        <p className="mt-0.5 max-w-[85%] whitespace-pre-line text-xs text-text-dim">
          {message.detail}
        </p>
      )}
    </li>
  );
}

function Conversation({ tasks }: { tasks: TaskInfo[] }) {
  const messages = useMessagesStore((state) => state.messages);
  const end = useRef<HTMLLIElement>(null);
  const shown = messages.slice(-SHOWN_MESSAGES);
  useEffect(() => {
    end.current?.scrollIntoView?.({ block: "end" });
  }, [shown.length]);
  if (shown.length === 0) {
    return <p className="text-text-dim">Nothing yet. Type a command below, or try "help".</p>;
  }
  const byId = new Map(tasks.map((task) => [task.id, task]));
  // The task's outcome badge goes on its last reply only (not on a confirmation question).
  const lastReply = new Map<string, string>();
  for (const message of shown) {
    if (message.role === "ace" && message.task_id) lastReply.set(message.task_id, message.id);
  }
  return (
    <ol className="flex flex-col gap-2">
      {shown.map((message) => (
        <MessageRow
          key={message.id}
          message={message}
          task={
            message.task_id && lastReply.get(message.task_id) === message.id
              ? byId.get(message.task_id)
              : undefined
          }
        />
      ))}
      <li ref={end} aria-hidden="true" />
    </ol>
  );
}

function ConfirmCards({ client, tasks }: { client: IpcClient | null; tasks: TaskInfo[] }) {
  const pending = tasks
    .map((task) => task.confirmation)
    .filter((confirmation): confirmation is ConfirmationInfo => confirmation !== null)
    .reverse(); // oldest first
  // Mounted afresh for every new set of confirmations (see `key` below), so this starts now.
  const [now, setNow] = useState(() => Date.now());
  const [busy, setBusy] = useState<string | null>(null);
  useEffect(() => {
    if (pending.length === 0) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [pending.length]);
  if (pending.length === 0) return null;

  const answer = (confirmation: ConfirmationInfo, choice: "yes" | "no") => {
    if (client === null) return;
    setBusy(confirmation.id);
    void answerConfirmation(client, confirmation.id, choice)
      .catch(() => {})
      .finally(() => setBusy(null));
  };

  return (
    <section aria-label="Confirmations" className="flex flex-col gap-2">
      {pending.map((confirmation) => (
        <ConfirmCard
          key={confirmation.id}
          action={confirmation.prompt}
          secondsLeft={secondsLeft(confirmation.expires_at, now)}
          busy={busy === confirmation.id || client === null}
          onConfirm={() => answer(confirmation, "yes")}
          onCancel={() => answer(confirmation, "no")}
        />
      ))}
    </section>
  );
}

function CurrentTask({ client, task }: { client: IpcClient | null; task: TaskInfo | null }) {
  if (task === null) return <p className="text-text-dim">No task running.</p>;
  const look = taskLook(task);
  const active = isActive(task);
  return (
    <>
      <div className="mb-1 flex items-center gap-2">
        <p className="min-w-0 flex-1 truncate font-medium">{task.utterance}</p>
        <Chip tone={look.tone}>{look.label}</Chip>
      </div>
      <StepList steps={toStepView(task)} />
      <div className="mt-2 flex gap-2">
        <Button size="sm" disabled title="Show me arrives with the agent runtime (S17)">
          Show me
        </Button>
        <Button
          size="sm"
          variant="danger"
          disabled={!active || client === null}
          onClick={() => {
            if (client !== null) void cancelTask(client, task.id).catch(() => {});
          }}
        >
          Stop
        </Button>
      </div>
    </>
  );
}

export function SidebarWindow({
  client = null,
  initialOpen = false,
}: {
  client?: IpcClient | null;
  initialOpen?: boolean;
}) {
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
  const tasks = useTasksStore((state) => state.tasks);
  const current = tasks.find(isActive) ?? tasks[0] ?? null;
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

  const send = (text: string) => {
    setHistory((entries) => [...entries.slice(-49), text]);
    if (client === null) {
      setNote("Not connected to ACE's core yet; this command was not sent.");
      return;
    }
    setNote(null);
    submitCommand(client, text).catch((error: unknown) => {
      setNote(`Couldn't send it: ${error instanceof Error ? error.message : String(error)}`);
    });
  };

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
            <Conversation tasks={tasks} />
          </section>

          <section aria-label="Current task">
            <Heading className="mb-1">
              {current && !isActive(current) ? "Last task" : "Current task"}
            </Heading>
            <CurrentTask client={client} task={current} />
          </section>

          <section aria-label="Background jobs">
            <Heading className="mb-1">Background jobs</Heading>
            <p className="text-text-dim">None. Background tasks arrive in stage S17.</p>
          </section>

          <ConfirmCards
            key={tasks.map((task) => task.confirmation?.id ?? "").join("")}
            client={client}
            tasks={tasks}
          />

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
              onSubmit={send}
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
