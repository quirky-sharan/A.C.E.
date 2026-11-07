// The overlay windows' calls into the desktop shell (S06, D-55). Each command is allowed only for
// the window that needs it (capabilities/orb.json, capabilities/sidebar.json).

import { invoke } from "@tauri-apps/api/core";

/** Sent by the shell to the orb window when the orb should appear or disappear. */
export const ORB_EVENT = "ace://overlay-orb";
/** Sent by the shell to the sidebar window when it opens or closes. */
export const SIDEBAR_EVENT = "ace://overlay-sidebar";

export type Edge = "right" | "left";

export interface OrbEvent {
  visible: boolean;
}

export interface SidebarEvent {
  open: boolean;
  /** True when summoned by hotkey: focus the text input. */
  focus: boolean;
  edge: Edge;
}

/** What a freshly loaded overlay page should show (events sent before it loaded are missed). */
export interface OverlayView {
  orbVisible: boolean;
  sidebarOpen: boolean;
  edge: Edge;
}

export interface HitRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export const getOverlayState = () => invoke<OverlayView>("overlay_state");
/** Where this window is clickable (CSS pixels); everything else lets clicks through. */
export const reportHitRects = (rects: HitRect[]) => invoke<void>("overlay_hit_rects", { rects });
export const orbClicked = () => invoke<void>("overlay_orb_clicked");
export const dragOrb = (phase: "start" | "end") => invoke<number | null>("overlay_drag", { phase });
export const openControlCenter = () => invoke<void>("open_control_center");
/** Close the sidebar (focus goes back at once); the panel then slides out. */
export const closeSidebar = () => invoke<void>("overlay_close_sidebar");
/** The panel finished sliding out: the shell hides the window (unless it was opened again). */
export const sidebarHidden = () => invoke<void>("overlay_sidebar_hidden");
/** Before a command or an answer: the app it opens or switches to may come to the front (D-57). */
export const allowForeground = () => invoke<void>("overlay_allow_foreground");
export const focusSidebarInput = () => invoke<void>("overlay_focus_input");
export const hideOverlayFor = (minutes: number) => invoke<void>("overlay_hide_for", { minutes });
export const reportSummonFocus = () => invoke<number | null>("overlay_report_focus");
export const overlayInput = (action: "mic_mute") => invoke<void>("overlay_input", { action });
