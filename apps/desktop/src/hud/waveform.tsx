// Level-driven waveform (§14.4): bars drawn on a canvas only when new levels arrive, at most
// 30 times a second. There is no animation loop, so a silent waveform costs nothing.

import { useEffect, useRef } from "react";

export const MAX_FPS = 30;
const FRAME_MS = 1000 / MAX_FPS;

export interface WaveformProps {
  /** Recent audio levels, oldest first, each from 0 to 1. */
  levels: number[];
  width?: number;
  height?: number;
  color?: string;
}

export function Waveform({
  levels,
  width = 240,
  height = 48,
  color = "var(--color-primary)",
}: WaveformProps) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const lastDraw = useRef(0);
  const trailing = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const draw = () => {
      lastDraw.current = performance.now();
      trailing.current = null;
      paint(canvas.current, levels);
    };
    const wait = FRAME_MS - (performance.now() - lastDraw.current);
    if (trailing.current !== null) clearTimeout(trailing.current);
    if (wait <= 0) {
      draw();
    } else {
      trailing.current = setTimeout(draw, wait);
    }
    return () => {
      if (trailing.current !== null) clearTimeout(trailing.current);
    };
  }, [levels]);

  return (
    <canvas
      ref={canvas}
      width={width}
      height={height}
      role="img"
      aria-label="Audio level"
      data-bars={levels.length}
      className="block"
      style={{ color }}
    />
  );
}

function paint(canvas: HTMLCanvasElement | null, levels: number[]): void {
  const context = canvas?.getContext("2d");
  if (!canvas || !context) return;
  const { width, height } = canvas;
  context.clearRect(0, 0, width, height);
  context.fillStyle = getComputedStyle(canvas).color;
  const bars = Math.max(levels.length, 1);
  const gap = 2;
  const barWidth = Math.max((width - gap * (bars - 1)) / bars, 1);
  levels.forEach((raw, index) => {
    const level = Math.min(Math.max(raw, 0), 1);
    const barHeight = Math.max(level * height, 2);
    context.fillRect(index * (barWidth + gap), (height - barHeight) / 2, barWidth, barHeight);
  });
  if (levels.length === 0) {
    context.fillRect(0, height / 2 - 1, width, 2); // silence: a flat line
  }
}
