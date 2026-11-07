// Test builders for S07 data: tasks, steps, confirmations and messages as the core sends them,
// plus a client that records requests.

import type { IpcClient } from "../ipc/client";
import type { ConfirmationInfo, MessageInfo, StepInfo, TaskInfo } from "../ipc/generated";

export function makeStep(overrides: Partial<StepInfo> = {}): StepInfo {
  return {
    id: "s1",
    idx: 0,
    skill_id: "apps.open",
    label: "Open spotify",
    tier: "T1",
    status: "running",
    started_at: null,
    finished_at: null,
    error_code: null,
    ...overrides,
  };
}

export function makeTask(overrides: Partial<TaskInfo> = {}): TaskInfo {
  return {
    id: "t1",
    conversation_id: "c1",
    origin: "text",
    utterance: "open spotify",
    intent: "apps.open",
    mode: "balanced",
    status: "running",
    created_at: "2026-11-07T12:00:00.000000Z",
    started_at: null,
    finished_at: null,
    result_summary: null,
    error_code: null,
    steps: [makeStep()],
    confirmation: null,
    ...overrides,
  };
}

export function makeConfirmation(overrides: Partial<ConfirmationInfo> = {}): ConfirmationInfo {
  return {
    id: "k1",
    task_id: "t1",
    step_id: "s1",
    prompt: "Run the demo dangerous action",
    requested_at: "2026-11-07T12:00:00.000000Z",
    expires_at: new Date(Date.now() + 30_000).toISOString(),
    ...overrides,
  };
}

export function makeMessage(overrides: Partial<MessageInfo> = {}): MessageInfo {
  return {
    id: "m1",
    conversation_id: "c1",
    ts: "2026-11-07T12:00:00.000000Z",
    role: "user",
    text: "echo hello",
    source: "text",
    detail: null,
    task_id: null,
    reply_to: null,
    ...overrides,
  };
}

/** A client whose `request` records every call and answers from `answers` (else rejects). */
export function requestClient(answers: Record<string, unknown> = {}) {
  const requests: [string, unknown][] = [];
  const client = {
    request: (method: string, params: unknown) => {
      requests.push([method, params]);
      return method in answers
        ? Promise.resolve(answers[method])
        : Promise.reject(new Error("not connected"));
    },
  };
  return { client: client as unknown as IpcClient, requests };
}
