import { describe, expect, it } from "vitest";

// S00 placeholder: proves the UI test runner works. Real component tests start in S05.
describe("desktop test harness", () => {
  it("runs TypeScript tests", () => {
    const sum = (a: number, b: number): number => a + b;
    expect(sum(2, 3)).toBe(5);
  });
});
