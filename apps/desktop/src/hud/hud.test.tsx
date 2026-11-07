import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ConversationState } from "../ipc/generated";
import { useNotificationsStore } from "../state/stores";
import { ClarifyCard, ConfirmCard, StepList } from "./cards";
import { TextInput, Toast, TOAST_MS, ToastViewport } from "./feedback";
import { Orb, ORB_LOOKS } from "./orb";
import { Button, Chip, Panel, StatusDot, Toggle } from "./primitives";
import { Waveform } from "./waveform";

describe("primitives", () => {
  it("panel, chip and dot carry their tone and accessible names", () => {
    render(
      <>
        <Panel title="Health" tone="warning">
          body
        </Panel>
        <Chip tone="success">Connected</Chip>
        <StatusDot tone="danger" label="core: down" />
      </>,
    );
    expect(screen.getByRole("region", { name: "Health" }).dataset.tone).toBe("warning");
    expect(screen.getByText("Connected").dataset.tone).toBe("success");
    expect(screen.getByRole("img", { name: "core: down" }).dataset.tone).toBe("danger");
  });

  it("buttons default to type=button and respect disabled", () => {
    const click = vi.fn();
    render(
      <>
        <Button onClick={click}>Go</Button>
        <Button variant="danger" disabled onClick={click}>
          Stop
        </Button>
      </>,
    );
    const go = screen.getByRole("button", { name: "Go" });
    expect(go.getAttribute("type")).toBe("button");
    fireEvent.click(go);
    fireEvent.click(screen.getByRole("button", { name: "Stop" }));
    expect(click).toHaveBeenCalledTimes(1);
  });

  it("toggle is a labelled switch", () => {
    const change = vi.fn();
    render(<Toggle label="Do not disturb" checked={false} onCheckedChange={change} />);
    const control = screen.getByRole("switch", { name: "Do not disturb" });
    expect(control.getAttribute("aria-checked")).toBe("false");
    fireEvent.click(control);
    expect(change).toHaveBeenCalledWith(true);
  });

  it("a disabled toggle ignores clicks", () => {
    const change = vi.fn();
    render(<Toggle label="Locked" checked onCheckedChange={change} disabled />);
    fireEvent.click(screen.getByRole("switch", { name: "Locked" }));
    expect(change).not.toHaveBeenCalled();
  });
});

describe("Orb", () => {
  it.each(Object.entries(ORB_LOOKS))("shows the %s state", (state, look) => {
    render(<Orb state={state as ConversationState} animate />);
    const orb = screen.getByRole("img", { name: `ACE: ${look.label}` });
    expect(orb.dataset.state).toBe(state);
    expect(orb.dataset.motion).toBe(look.motion);
    expect(orb.dataset.animate).toBe(look.motion === "none" ? "false" : "true");
    expect(orb.querySelector(".orb-slash") !== null).toBe(state === "muted");
    expect(orb.querySelector(".orb-progress") !== null).toBe(state === "acting");
  });

  it("stays still when animation is off, and shows 'not connected' without a state", () => {
    render(<Orb state={null} animate={false} />);
    const orb = screen.getByRole("img", { name: "ACE: Not connected" });
    expect(orb.dataset.state).toBe("offline");
    expect(orb.dataset.animate).toBe("false");
  });
});

describe("Waveform", () => {
  it("renders without a canvas backend (jsdom) and reports its bars", () => {
    const { rerender } = render(<Waveform levels={[]} />);
    expect(screen.getByRole("img", { name: "Audio level" }).dataset.bars).toBe("0");
    rerender(<Waveform levels={[0.2, 0.8, 1.4, -1]} />);
    expect(screen.getByRole("img", { name: "Audio level" }).dataset.bars).toBe("4");
  });
});

describe("cards", () => {
  it("step list badges each status", () => {
    render(
      <StepList
        steps={[
          { id: "a", label: "Done", status: "done" },
          { id: "b", label: "Warn", status: "warning" },
          { id: "c", label: "Fail", status: "failed" },
          { id: "d", label: "Again", status: "retrying" },
          { id: "e", label: "Now", status: "running" },
          { id: "f", label: "Later", status: "pending" },
        ]}
      />,
    );
    expect(screen.getByRole("img", { name: "done" }).textContent).toBe("✓");
    expect(screen.getByRole("img", { name: "warning" }).textContent).toBe("⚠");
    expect(screen.getByRole("img", { name: "failed" }).textContent).toBe("✗");
    expect(screen.getByRole("img", { name: "retrying" }).textContent).toBe("↺");
    expect(screen.getAllByRole("listitem").map((item) => item.dataset.status)).toEqual([
      "done",
      "warning",
      "failed",
      "retrying",
      "running",
      "pending",
    ]);
  });

  it("confirm card restates the action and answers yes / no", () => {
    const yes = vi.fn();
    const no = vi.fn();
    render(
      <ConfirmCard
        action="Send to Mom: 'home by 8'"
        secondsLeft={21}
        onConfirm={yes}
        onCancel={no}
      />,
    );
    expect(screen.getByText("Send to Mom: 'home by 8'")).toBeTruthy();
    expect(screen.getByText("Cancels by itself in 21 s")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Yes" }));
    fireEvent.click(screen.getByRole("button", { name: "No" }));
    expect(yes).toHaveBeenCalledOnce();
    expect(no).toHaveBeenCalledOnce();
  });

  it("a busy confirm card cannot be answered twice", () => {
    const yes = vi.fn();
    render(<ConfirmCard action="Restart the PC" busy onConfirm={yes} onCancel={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Yes" }));
    expect(yes).not.toHaveBeenCalled();
  });

  it("clarify card offers each option", () => {
    const choose = vi.fn();
    render(
      <ClarifyCard
        question="Which Spotify?"
        options={[
          { id: "store", label: "Store app" },
          { id: "web", label: "In Chrome" },
        ]}
        onChoose={choose}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "In Chrome" }));
    expect(choose).toHaveBeenCalledWith("web");
    expect(screen.queryByRole("button", { name: "Cancel" })).toBeNull();
  });
});

describe("feedback", () => {
  beforeEach(() => {
    useNotificationsStore.setState(useNotificationsStore.getInitialState());
  });

  it("toast shows its tone, actions and dismiss button", () => {
    const dismiss = vi.fn();
    const snooze = vi.fn();
    render(
      <Toast
        tone="warning"
        title="Quota low"
        message="12 left"
        actions={[{ label: "Snooze", onClick: snooze }]}
        onDismiss={dismiss}
      />,
    );
    expect(screen.getByRole("status").dataset.tone).toBe("warning");
    fireEvent.click(screen.getByRole("button", { name: "Snooze" }));
    fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(snooze).toHaveBeenCalledOnce();
    expect(dismiss).toHaveBeenCalledOnce();
  });

  it("toasts in the viewport close by themselves", () => {
    vi.useFakeTimers();
    try {
      render(<ToastViewport />);
      act(() => {
        useNotificationsStore.getState().push({ tone: "info", title: "Image ready" });
      });
      expect(screen.getByText("Image ready")).toBeTruthy();
      act(() => {
        vi.advanceTimersByTime(TOAST_MS);
      });
      expect(useNotificationsStore.getState().items).toEqual([]);
    } finally {
      vi.useRealTimers();
    }
  });

  it("text input sends on Enter, clears on Esc and walks history", () => {
    const submit = vi.fn();
    const escape = vi.fn();
    render(
      <TextInput
        label="Command"
        history={["open spotify", "what time is it"]}
        onSubmit={submit}
        onEscape={escape}
      />,
    );
    const input = screen.getByRole<HTMLInputElement>("textbox", { name: "Command" });

    fireEvent.change(input, { target: { value: "  echo hello  " } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(submit).toHaveBeenCalledWith("echo hello");
    expect(input.value).toBe("");

    fireEvent.keyDown(input, { key: "Enter" }); // empty: nothing sent
    expect(submit).toHaveBeenCalledOnce();

    fireEvent.keyDown(input, { key: "ArrowUp" });
    expect(input.value).toBe("what time is it");
    fireEvent.keyDown(input, { key: "ArrowUp" });
    expect(input.value).toBe("open spotify");
    fireEvent.keyDown(input, { key: "ArrowUp" });
    expect(input.value).toBe("open spotify");
    fireEvent.keyDown(input, { key: "ArrowDown" });
    expect(input.value).toBe("what time is it");
    fireEvent.keyDown(input, { key: "ArrowDown" });
    expect(input.value).toBe("");

    fireEvent.change(input, { target: { value: "draft" } });
    fireEvent.keyDown(input, { key: "Escape" });
    expect(input.value).toBe("");
    expect(escape).toHaveBeenCalledOnce();
  });
});
