// Devices (§14.5, S09): choose the microphone and speakers, test the microphone for 5 seconds with
// a live level meter, play it back, play a test sound, and mute. Until the wake word (S12) ACE opens
// the microphone only while testing here (D-58).

import { useCallback, useEffect, useState } from "react";

import { Button, Chip, Panel } from "../hud";
import type { IpcClient } from "../ipc/client";
import type { DevicesResult } from "../ipc/generated";

export const TEST_SECONDS = 5;
const DEFAULT_CHOICE = "";

function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function DeviceSelect({
  label,
  devices,
  chosen,
  onChange,
}: {
  label: string;
  devices: DevicesResult["inputs"];
  chosen: string | null;
  onChange: (name: string | null) => void;
}) {
  const fallback = devices.find((device) => device.is_default)?.name;
  return (
    <label className="flex flex-col gap-1">
      <span className="text-text-dim">{label}</span>
      <select
        value={chosen ?? DEFAULT_CHOICE}
        onChange={(event) =>
          onChange(event.target.value === DEFAULT_CHOICE ? null : event.target.value)
        }
        className="rounded-sm border border-line bg-bg px-3 py-2 text-text focus:border-primary focus:outline-none"
      >
        <option value={DEFAULT_CHOICE}>Windows default{fallback ? ` (${fallback})` : ""}</option>
        {devices.map((device) => (
          <option key={device.name} value={device.name}>
            {device.name}
          </option>
        ))}
      </select>
    </label>
  );
}

export function Devices({ client }: { client: IpcClient | null }) {
  const [info, setInfo] = useState<DevicesResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [level, setLevel] = useState(0);
  const [recording, setRecording] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [canPlay, setCanPlay] = useState(false);

  const reload = useCallback(() => {
    if (client === null) return;
    client
      .request("devices.list", {})
      .then((answer) => {
        setInfo(answer);
        setError(null);
      })
      .catch((reason: unknown) => setError(message(reason)));
  }, [client]);

  useEffect(() => {
    if (client === null) return;
    const timer = window.setTimeout(reload, 0);
    const stops = [
      client.onEvent("audio.level", (payload) => setLevel(payload.level)),
      client.onEvent("state.changed", () => reload()), // mute from the tray or a hotkey
    ];
    return () => {
      window.clearTimeout(timer);
      stops.forEach((stop) => stop());
    };
  }, [client, reload]);

  if (client === null) return <p className="text-text-dim">Not connected to ACE's core.</p>;
  if (info !== null && !info.available) {
    return <p className="text-text-dim">Audio is not available on this system.</p>;
  }

  const choose = (kind: "input" | "output", name: string | null) => {
    void client
      .request("devices.select", { kind, name })
      .then(reload)
      .catch((reason: unknown) => setError(message(reason)));
  };

  const test = () => {
    setRecording(true);
    setResult(null);
    client
      .request("devices.record_test", { seconds: TEST_SECONDS })
      .then((answer) => {
        if (!answer.ok) {
          setResult(answer.error ?? "The test failed.");
          return;
        }
        setCanPlay(true);
        setResult(
          answer.peak < 0.02
            ? "Nothing was heard. Check the microphone, or Windows' microphone privacy setting."
            : `Recorded ${answer.seconds} s, loudest point ${Math.round(answer.peak * 100)} %.`,
        );
      })
      .catch((reason: unknown) => setResult(message(reason)))
      .finally(() => {
        setRecording(false);
        setLevel(0);
      });
  };

  const run = (method: "devices.play_test" | "devices.stop" | "devices.earcon") => {
    const request =
      method === "devices.earcon"
        ? client.request("devices.earcon", { name: "test" })
        : client.request(method, {});
    void request
      .then((answer) => {
        if (!answer.ok && answer.error) setResult(answer.error);
      })
      .catch((reason: unknown) => setResult(message(reason)));
  };

  const muted = info?.muted ?? false;
  return (
    <div className="flex max-w-2xl flex-col gap-4">
      {error && <p className="text-danger">Couldn't read the devices: {error}</p>}
      <Panel
        title="Microphone"
        actions={
          <Chip tone={muted ? "warning" : info?.capturing ? "danger" : "neutral"}>
            {muted ? "Muted" : info?.capturing || recording ? "In use" : "Closed"}
          </Chip>
        }
      >
        {info && (
          <DeviceSelect
            label="Input device"
            devices={info.inputs}
            chosen={info.input}
            onChange={(name) => choose("input", name)}
          />
        )}
        <div
          role="meter"
          aria-label="Microphone level"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(level * 100)}
          className="mt-3 h-2 w-full overflow-hidden rounded-sm bg-bg"
        >
          <div
            className="h-full bg-primary transition-[width] duration-75"
            style={{ width: `${level * 100}%` }}
          />
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <Button variant="primary" disabled={recording || muted} onClick={test}>
            {recording ? "Recording… speak now" : `Test microphone (${TEST_SECONDS} s)`}
          </Button>
          <Button disabled={!canPlay || recording} onClick={() => run("devices.play_test")}>
            Play back
          </Button>
          <Button
            onClick={() => {
              void client
                .request("devices.mute", { muted: !muted })
                .then(reload)
                .catch((reason: unknown) => setError(message(reason)));
            }}
          >
            {muted ? "Unmute mic" : "Mute mic"}
          </Button>
        </div>
        {result && (
          <p className="mt-2" aria-live="polite">
            {result}
          </p>
        )}
        <p className="mt-3 text-xs text-text-dim">
          ACE opens the microphone only while you test it here. Always-on listening starts with the
          "Hey Ace" wake word (S12). Recordings stay in memory and are never sent anywhere.
        </p>
      </Panel>
      <Panel title="Speakers">
        {info && (
          <DeviceSelect
            label="Output device"
            devices={info.outputs}
            chosen={info.output}
            onChange={(name) => choose("output", name)}
          />
        )}
        <div className="mt-3 flex gap-2">
          <Button onClick={() => run("devices.earcon")}>Play test sound</Button>
          <Button onClick={() => run("devices.stop")}>Stop</Button>
        </div>
      </Panel>
    </div>
  );
}
