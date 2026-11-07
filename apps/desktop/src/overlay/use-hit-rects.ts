// Tells the shell where an overlay window's clickable parts are, whenever they appear, move or
// resize (D-40: the shell polls the cursor and lets clicks pass through everything else).

import { useEffect, type RefObject } from "react";

import { reportHitRects, type HitRect } from "./overlay-api";

export function rectOf(element: Element): HitRect {
  const box = element.getBoundingClientRect();
  return { x: box.left, y: box.top, width: box.width, height: box.height };
}

/** Report the rectangles of `refs` while `active`; report none (all click-through) otherwise. */
export function useHitRects(refs: RefObject<Element | null>[], active: boolean): void {
  useEffect(() => {
    const elements = active
      ? refs.map((ref) => ref.current).filter((element) => element !== null)
      : [];
    const report = () => {
      void reportHitRects(elements.map(rectOf)).catch(() => {});
    };
    report();
    const observer = new ResizeObserver(report);
    elements.forEach((element) => observer.observe(element));
    window.addEventListener("resize", report);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", report);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- refs are stable objects
  }, [active]);
}
