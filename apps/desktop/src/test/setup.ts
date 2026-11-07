import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// Vitest runs without globals, so Testing Library cannot clean up by itself.
afterEach(() => {
  cleanup();
});

// jsdom has no canvas backend; the Waveform copes with a missing 2D context.
HTMLCanvasElement.prototype.getContext = (() =>
  null) as typeof HTMLCanvasElement.prototype.getContext;

// jsdom has no ResizeObserver; the overlay's hit-rect reporting only needs the API to exist.
class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
globalThis.ResizeObserver ??= ResizeObserverStub as unknown as typeof ResizeObserver;

// jsdom elements may lack pointer capture; the orb calls it on every press.
Element.prototype.setPointerCapture ??= () => {};
