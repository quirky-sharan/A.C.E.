import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { IpcClient } from "../ipc/client";
import { Devices } from "./devices";

const listed = {
  available: true,
  muted: false,
  capturing: false,
  input: null,
  output: "Headphones (USB)",
  inputs: [
    { name: "Microphone Array (Realtek(R) Audio)", is_default: true },
    { name: "Headset (Bluetooth)", is_default: false },
  ],
  outputs: [
    { name: "Speakers (Realtek(R) Audio)", is_default: true },
    { name: "Headphones (USB)", is_default: false },
  ],
};

/** A client with scripted answers that also lets the test send events. */
function fake(answers: Record<string, unknown>) {
  const requests: [string, unknown][] = [];
  const listeners = new Map<string, (payload: unknown) => void>();
  const client = {
    request: (method: string, params: unknown) => {
      requests.push([method, params]);
      const answer = answers[method];
      return answer instanceof Promise ? answer : Promise.resolve(answer);
    },
    onEvent: (name: string, listener: (payload: unknown) => void) => {
      listeners.set(name, listener);
      return () => listeners.delete(name);
    },
  };
  return {
    client: client as unknown as IpcClient,
    requests,
    emit: (name: string, payload: unknown) => listeners.get(name)?.(payload),
  };
}

describe("Devices page", () => {
  it("shows the devices with the Windows default and the saved choice", async () => {
    const { client, requests } = fake({
      "devices.list": listed,
      "devices.select": { saved: true },
    });
    render(<Devices client={client} />);
    const input = await screen.findByRole<HTMLSelectElement>("combobox", { name: "Input device" });
    expect(input.value).toBe("");
    expect(input.textContent).toContain("Windows default (Microphone Array (Realtek(R) Audio))");
    const output = screen.getByRole<HTMLSelectElement>("combobox", { name: "Output device" });
    expect(output.value).toBe("Headphones (USB)");
    fireEvent.change(input, { target: { value: "Headset (Bluetooth)" } });
    await vi.waitFor(() =>
      expect(requests).toContainEqual([
        "devices.select",
        { kind: "input", name: "Headset (Bluetooth)" },
      ]),
    );
  });

  it("tests the microphone with a live meter, then plays it back", async () => {
    let finish: (value: unknown) => void = () => {};
    const recording = new Promise((resolve) => (finish = resolve));
    const { client, requests, emit } = fake({
      "devices.list": listed,
      "devices.record_test": recording,
      "devices.play_test": { ok: true, error: null, seconds: 5 },
    });
    render(<Devices client={client} />);
    fireEvent.click(await screen.findByRole("button", { name: "Test microphone (5 s)" }));
    expect(screen.getByRole("button", { name: "Recording… speak now" })).toBeTruthy();
    act(() => emit("audio.level", { level: 0.6 }));
    expect(
      screen.getByRole("meter", { name: "Microphone level" }).getAttribute("aria-valuenow"),
    ).toBe("60");
    await act(async () => finish({ ok: true, error: null, seconds: 5, peak: 0.42, level: 0.5 }));
    expect(screen.getByText("Recorded 5 s, loudest point 42 %.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Play back" }));
    await vi.waitFor(() => expect(requests.map(([m]) => m)).toContain("devices.play_test"));
  });

  it("explains a silent test and shows mute", async () => {
    const { client } = fake({
      "devices.list": { ...listed, muted: true },
      "devices.record_test": { ok: true, error: null, seconds: 5, peak: 0.001, level: 0 },
    });
    render(<Devices client={client} />);
    expect(await screen.findByText("Muted")).toBeTruthy();
    expect(
      screen.getByRole<HTMLButtonElement>("button", { name: "Test microphone (5 s)" }).disabled,
    ).toBe(true);
    expect(screen.getByRole("button", { name: "Unmute mic" })).toBeTruthy();
  });

  it("says when audio is not available", async () => {
    const { client } = fake({ "devices.list": { ...listed, available: false } });
    render(<Devices client={client} />);
    expect(await screen.findByText("Audio is not available on this system.")).toBeTruthy();
  });
});
