// The edge orb (§14.1, S06): shows ACE's state; click opens / closes the sidebar, right-click opens
// the Control Center, dragging moves it along the screen edge (the position is saved in the core).
// While the orb is hidden, the shell hides the window too, and the page draws nothing.

import { listen } from "@tauri-apps/api/event";
import { useEffect, useRef, useState, type PointerEvent } from "react";

import { Orb, useOrbAnimating } from "../hud";
import type { IpcClient } from "../ipc/client";
import { saveSetting } from "../state/core-link";
import { useCoreStore } from "../state/stores";
import {
  dragOrb,
  getOverlayState,
  openControlCenter,
  orbClicked,
  ORB_EVENT,
  type OrbEvent,
} from "./overlay-api";
import { useHitRects } from "./use-hit-rects";

/** A press that moves farther than this (CSS px) is a drag, not a click. */
export const DRAG_THRESHOLD = 4;
export const ORB_SIZE = 56;

export function OrbWindow({ client }: { client: IpcClient | null }) {
  const conversation = useCoreStore((state) => state.state?.conversation ?? null);
  const [visible, setVisible] = useState(false);
  const animate = useOrbAnimating(visible ? conversation : null);
  const button = useRef<HTMLButtonElement>(null);
  const press = useRef<{ x: number; y: number; dragging: boolean } | null>(null);
  const [dragging, setDragging] = useState(false);
  useHitRects([button], visible);

  useEffect(() => {
    let active = true;
    let eventSeen = false;
    const stop = listen<OrbEvent>(ORB_EVENT, ({ payload }) => {
      eventSeen = true;
      if (active) setVisible(payload.visible);
    }).catch(() => () => {});
    getOverlayState()
      .then((view) => {
        if (active && !eventSeen) setVisible(view.orbVisible); // an event is newer
      })
      .catch(() => {});
    return () => {
      active = false;
      void stop.then((unlisten) => unlisten());
    };
  }, []);

  const onPointerDown = (event: PointerEvent<HTMLButtonElement>) => {
    if (event.button !== 0) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    press.current = { x: event.screenX, y: event.screenY, dragging: false };
  };

  const onPointerMove = (event: PointerEvent<HTMLButtonElement>) => {
    const current = press.current;
    if (current === null || current.dragging) return;
    if (Math.hypot(event.screenX - current.x, event.screenY - current.y) > DRAG_THRESHOLD) {
      current.dragging = true;
      setDragging(true);
      void dragOrb("start");
    }
  };

  const onPointerUp = () => {
    const current = press.current;
    press.current = null;
    if (current === null) return;
    if (!current.dragging) {
      void orbClicked();
      return;
    }
    setDragging(false);
    void dragOrb("end").then((orbY) => {
      if (orbY !== null && client !== null) {
        void saveSetting(client, "overlay.orb_y", orbY).catch(() => {});
      }
    });
  };

  return (
    <div className="flex h-full w-full items-center justify-center">
      {visible && (
        <button
          ref={button}
          type="button"
          aria-label="Open the ACE sidebar"
          title="ACE — click to open, right-click for the Control Center, drag to move"
          className={dragging ? "cursor-grabbing rounded-full" : "cursor-pointer rounded-full"}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onContextMenu={(event) => {
            event.preventDefault();
            void openControlCenter();
          }}
        >
          <Orb state={conversation} animate={animate} size={ORB_SIZE} />
        </button>
      )}
    </div>
  );
}
