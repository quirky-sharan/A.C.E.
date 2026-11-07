import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// Vitest runs without globals, so Testing Library cannot clean up by itself.
afterEach(() => {
  cleanup();
});

// jsdom has no canvas backend; the Waveform copes with a missing 2D context.
HTMLCanvasElement.prototype.getContext = (() =>
  null) as typeof HTMLCanvasElement.prototype.getContext;
