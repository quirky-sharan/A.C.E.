// The Control Center's pages (§14.5). Each stub names the stage that fills it in.

import {
  AudioLines,
  Bell,
  Brain,
  ClockArrowLeft,
  Cpu,
  FolderGit2,
  Gamepad2,
  Globe,
  Info,
  KeyRound,
  LayoutDashboard,
  Mic,
  Palette,
  Repeat,
  Shapes,
  ShieldCheck,
  Stethoscope,
  Users,
  type LucideIcon,
} from "lucide-react";

export interface PageInfo {
  id: string;
  title: string;
  summary: string;
  /** The stage that builds this page; null when it already works. */
  stage: string | null;
  icon: LucideIcon;
  devOnly?: boolean;
}

export const PAGES: readonly PageInfo[] = [
  {
    id: "dashboard",
    title: "Dashboard",
    summary: "Status, recent tasks, quotas and latency.",
    stage: null,
    icon: LayoutDashboard,
  },
  {
    id: "history",
    title: "History",
    summary: "Search conversations and tasks, with verification details.",
    stage: null,
    icon: ClockArrowLeft,
  },
  {
    id: "memory",
    title: "Memory",
    summary: "What ACE remembers about you: view, edit, delete.",
    stage: "S31",
    icon: Brain,
  },
  {
    id: "routines",
    title: "Routines",
    summary: "One phrase, a time or an event runs many actions.",
    stage: "S32",
    icon: Repeat,
  },
  {
    id: "skills",
    title: "Skills & Permissions",
    summary: "Enable or disable skills, see their tiers, manage pre-approvals.",
    stage: null,
    icon: ShieldCheck,
  },
  {
    id: "accounts",
    title: "Accounts & Contacts",
    summary: "Which account each service uses, and ACE's own contact book.",
    stage: "S25, S29",
    icon: Users,
  },
  {
    id: "providers",
    title: "Providers & Keys",
    summary: "Add, test and watch the quotas of AI providers.",
    stage: "S15",
    icon: KeyRound,
  },
  {
    id: "voice",
    title: "Voice",
    summary: "Voice audition, speaking speed, wake-word sensitivity.",
    stage: "S11–S12",
    icon: AudioLines,
  },
  {
    id: "devices",
    title: "Devices",
    summary: "Choose and test the microphone and speakers.",
    stage: null,
    icon: Mic,
  },
  {
    id: "models",
    title: "Models",
    summary: "Downloads and graphics memory of the local models.",
    stage: "S14",
    icon: Cpu,
  },
  {
    id: "bridge",
    title: "Browser Bridge",
    summary: "Chrome extension status, site self-tests and opt-ins.",
    stage: "S24–S25",
    icon: Globe,
  },
  {
    id: "projects",
    title: "Projects",
    summary: "Your code projects and their commands.",
    stage: "S33",
    icon: FolderGit2,
  },
  {
    id: "games",
    title: "Games",
    summary: "Game mode and the games that trigger it.",
    stage: "S36",
    icon: Gamepad2,
  },
  {
    id: "notifications",
    title: "Notifications",
    summary: "Phone push (ntfy) setup with a QR code.",
    stage: "S37",
    icon: Bell,
  },
  {
    id: "appearance",
    title: "Appearance",
    summary: "Overlay skin, screen edge and opacity.",
    stage: "S06, S39",
    icon: Palette,
  },
  {
    id: "diagnostics",
    title: "Diagnostics",
    summary: "Logs, health checks, backups and restore, safe mode.",
    stage: "S41",
    icon: Stethoscope,
  },
  {
    id: "about",
    title: "About / Updates",
    summary: "Version, licences and updates.",
    stage: "S44",
    icon: Info,
  },
  {
    id: "gallery",
    title: "Component gallery",
    summary: "Every HUD component in every state (developer builds only).",
    stage: null,
    icon: Shapes,
    devOnly: true,
  },
];

export const DEFAULT_PAGE = "dashboard";

/** Pages shown in this build: the gallery only in development. */
export function visiblePages(dev: boolean): readonly PageInfo[] {
  return PAGES.filter((page) => dev || !page.devOnly);
}
