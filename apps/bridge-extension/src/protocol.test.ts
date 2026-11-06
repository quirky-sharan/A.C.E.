import { describe, expect, it } from "vitest";

import { BRIDGE_PROTOCOL_VERSION } from "./protocol";

describe("bridge protocol", () => {
  it("declares a positive integer version", () => {
    expect(Number.isInteger(BRIDGE_PROTOCOL_VERSION)).toBe(true);
    expect(BRIDGE_PROTOCOL_VERSION).toBeGreaterThan(0);
  });
});
