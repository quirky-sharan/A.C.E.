// Developer-only gallery (S05 task 7): every HUD component in every state. Not part of release
// builds (the Control Center loads it only when import.meta.env.DEV is true).

import { useState, type ReactNode } from "react";

import {
  Button,
  Chip,
  ClarifyCard,
  ConfirmCard,
  Orb,
  ORB_LOOKS,
  Panel,
  StatusDot,
  StepList,
  TextInput,
  Toast,
  Toggle,
  Waveform,
  type Tone,
} from "../hud";
import type { ConversationState } from "../ipc/generated";
import { useNotificationsStore, type TaskStep } from "../state/stores";

const TONES: Tone[] = ["neutral", "primary", "success", "warning", "danger", "violet", "orange"];
const STATES = Object.keys(ORB_LOOKS) as ConversationState[];
const STEPS: TaskStep[] = [
  { id: "1", label: "Find Spotify in the app index", status: "done" },
  { id: "2", label: "Launch it", status: "running" },
  { id: "3", label: "Check the window opened", status: "pending" },
  { id: "4", label: "Window title did not match at first", status: "warning" },
  { id: "5", label: "Retry with the Store app ID", status: "retrying" },
  { id: "6", label: "Could not focus the window", status: "failed" },
];
const LEVELS = {
  silent: [] as number[],
  quiet: Array.from({ length: 32 }, (_, n) => 0.1 + 0.05 * Math.sin(n / 2)),
  loud: Array.from({ length: 32 }, (_, n) => 0.55 + 0.4 * Math.sin(n / 1.7)),
};

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Panel title={title}>
      <div className="flex flex-wrap items-start gap-4">{children}</div>
    </Panel>
  );
}

export function Gallery() {
  const [animate, setAnimate] = useState(false);
  const [toggle, setToggle] = useState(true);
  const [log, setLog] = useState<string[]>([]);
  const push = useNotificationsStore((state) => state.push);
  const note = (entry: string) => setLog((entries) => [...entries.slice(-4), entry]);

  return (
    <div className="flex flex-col gap-4">
      <Section title="Orb — every conversation state">
        <div className="w-full">
          <Toggle
            label="Animate (as when ACE is active and the window is visible)"
            checked={animate}
            onCheckedChange={setAnimate}
          />
        </div>
        {[null, ...STATES].map((state) => (
          <figure
            key={state ?? "offline"}
            className="flex w-28 flex-col items-center gap-1 text-center"
          >
            <Orb
              state={state}
              animate={animate}
              size={64}
              progress={state === "acting" ? 0.6 : undefined}
            />
            <figcaption className="text-xs text-text-dim">
              {state === null ? "not connected" : ORB_LOOKS[state].label}
            </figcaption>
          </figure>
        ))}
      </Section>

      <Section title="Panel tones">
        {TONES.map((tone) => (
          <Panel key={tone} title={tone} tone={tone} className="w-40">
            <p className="text-text-dim">Panel</p>
          </Panel>
        ))}
      </Section>

      <Section title="Buttons">
        <Button variant="primary">Primary</Button>
        <Button>Ghost</Button>
        <Button variant="danger">Danger</Button>
        <Button variant="primary" disabled>
          Disabled
        </Button>
        <Button size="sm">Small</Button>
        <Button size="lg" variant="primary">
          Large
        </Button>
      </Section>

      <Section title="Toggles and chips">
        <Toggle label="On / off" checked={toggle} onCheckedChange={setToggle} />
        <Toggle label="Disabled off" checked={false} onCheckedChange={() => {}} disabled />
        <Toggle label="Disabled on" checked onCheckedChange={() => {}} disabled />
        <div className="flex flex-wrap gap-2">
          {TONES.map((tone) => (
            <Chip key={tone} tone={tone}>
              {tone}
            </Chip>
          ))}
        </div>
        <div className="flex items-center gap-2">
          {TONES.map((tone) => (
            <StatusDot key={tone} tone={tone} label={tone} />
          ))}
        </div>
      </Section>

      <Section title="Waveform">
        {Object.entries(LEVELS).map(([name, levels]) => (
          <figure key={name} className="flex flex-col gap-1">
            <Waveform levels={levels} />
            <figcaption className="text-xs text-text-dim">{name}</figcaption>
          </figure>
        ))}
      </Section>

      <Section title="Step list">
        <StepList steps={STEPS} />
      </Section>

      <Section title="Confirmation and clarification">
        <div className="w-80">
          <ConfirmCard
            action="Send to Mom on WhatsApp: “I'll be home by 8”"
            onConfirm={() => note("confirmed")}
            onCancel={() => note("cancelled")}
          />
        </div>
        <div className="w-80">
          <ConfirmCard
            action="Delete 3 files (1.2 MB) to the Recycle Bin"
            secondsLeft={24}
            onConfirm={() => note("confirmed")}
            onCancel={() => note("cancelled")}
          />
        </div>
        <div className="w-80">
          <ConfirmCard action="Restart the PC" busy onConfirm={() => {}} onCancel={() => {}} />
        </div>
        <div className="w-80">
          <ClarifyCard
            question="Which Spotify should I open?"
            options={[
              { id: "store", label: "Spotify (Store app)" },
              { id: "web", label: "Spotify in Chrome" },
            ]}
            onChoose={(id) => note(`chose ${id}`)}
            onCancel={() => note("clarify cancelled")}
          />
        </div>
      </Section>

      <Section title="Toasts">
        <Toast
          tone="info"
          title="Image ready"
          message="Gemini finished the poster."
          onDismiss={() => {}}
        />
        <Toast tone="success" title="Saved" message="Notes exported to Documents." />
        <Toast
          tone="warning"
          title="Quota low"
          message="Groq: 12 requests left today."
          actions={[{ label: "Snooze", onClick: () => note("snoozed") }]}
        />
        <Toast
          tone="danger"
          title="Site changed"
          message="The ChatGPT adapter needs an update."
          actions={[{ label: "Show", onClick: () => note("show") }]}
          onDismiss={() => {}}
        />
        <Button
          onClick={() =>
            push({
              tone: "info",
              title: "Hello from the gallery",
              message: "This toast closes after 6 s.",
            })
          }
        >
          Show a live toast
        </Button>
      </Section>

      <Section title="Text input">
        <div className="w-96">
          <TextInput
            label="Command"
            placeholder="Type a command, Enter to send"
            history={["open spotify", "what time is it"]}
            onSubmit={(text) => note(`sent: ${text}`)}
          />
        </div>
        <div className="w-96">
          <TextInput label="Disabled command" placeholder="Disabled" disabled onSubmit={() => {}} />
        </div>
      </Section>

      <Panel title="Gallery events">
        <p className="font-mono text-xs text-text-dim">
          {log.length ? log.join(" · ") : "Interact with a component to see its events here."}
        </p>
      </Panel>
    </div>
  );
}
