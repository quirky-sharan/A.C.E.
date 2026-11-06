# ACE — Master Plan & Specification

> The single source of truth for building **ACE**, a Windows desktop assistant that *operates* Sharan's PC by voice or text.
> Written for AI coding agents first and humans second. **Read §0 before doing anything.**

## STATUS

| Field | Value |
|---|---|
| Doc version | 1.1.0 |
| Doc created | 2026-11-06 |
| Last updated | 2026-11-06 |
| Owner / client | Sharan (ACE addresses Sharan as "Sharan" or "boss") |
| Project folder | `E:\A.C.E` |
| Current stage | **S01 — Core service skeleton** (in progress, branch `stage/s01-core-service`) |
| Last completed stage | S00 — Workspace & repository setup (approved by Sharan 2026-11-06) |
| Next milestone | M1 — Typed commands control the PC |
| Blocking user actions | none · pending, non-blocking: [USER-ACTION] run `tools/dev/set-dev-env.ps1` once in a normal PowerShell window (§17.4); create the GitHub repo to activate CI |

---

## §0 How to use this document

### 0.1 Reading order (every AI session, every time)
1. **STATUS** (above).
2. **§0** completely (rules, legend, Definition of Done).
3. **§4 Decision Log** — everything listed there is already decided. Do not re-decide.
4. The **current stage** in §18, plus every spec section that stage links to.
5. **§23 Progress Log** — at least the last 3 entries.
6. In your first reply, state: the current stage, what you will do this session, and which [VERIFY] items you will check.

### 0.2 Rules for AI builders [MUST]
- **R1 One stage at a time.** Only work on the stage named in STATUS. Do not start the next stage until the current stage's Definition of Done is met **and Sharan approves** moving on.
- **R2 Don't re-decide.** Items in §4 are decided. To change one: explain why, give options with a recommendation, get Sharan's explicit approval, then update §4 and every affected section in the same commit.
- **R3 Never guess APIs.** Before using any library, OS API, web endpoint, CSS selector, CLI flag or config key, check the official documentation for the exact pinned version. If you cannot verify it, say so and ask. Never invent function names, parameters or endpoints.
- **R4 Resolve [VERIFY] tags.** Every [VERIFY] item in the current stage must be checked against an official source before it is relied on. Record the outcome (confirmed / changed, source URL, date) in the Progress Log. If the fact changed, update this doc.
- **R5 Ask, don't assume.** If something is ambiguous, conflicting or impossible, stop and ask Sharan with concrete options and your recommendation.
- **R6 No scope creep.** Do not add features that are not in this doc. Put new ideas in §21 (Parked ideas) and mention them to Sharan.
- **R7 Security basics from day 1.** The §15.1 baseline is mandatory from S01 onward. Never weaken it "temporarily".
- **R8 No secrets anywhere.** Never commit or log API keys, OAuth tokens, cookies, passwords, contacts' phone numbers or emails. Secrets live only in Windows Credential Manager (via `keyring`).
- **R9 Tests are part of the work.** Every stage lists required tests. They must pass locally, and in CI for all non-hardware tests.
- **R10 Keep the doc true.** If implementation shows the doc is wrong, fix the doc (design changes need Sharan's approval first). Code and doc must never disagree.
- **R11 Small commits.** Prefix every commit with the stage ID, e.g. `[S07] add skill registry`. Never rewrite shared history.
- **R12 Boring, proven, permissive dependencies.** Check license compatibility (§6.4) before adding a dependency. Record new dependencies in the stage's Progress Log entry.
- **R13 OS access behind interfaces.** All Windows/hardware access goes through adapter interfaces in `ace_core/os/` so logic can be unit-tested with fakes.
- **R14 Disk discipline.** Caches, models, toolchains and build outputs live on `E:` (§17.4). State the size before downloading anything larger than 200 MB.
- **R15 Don't break working features.** Run the full non-hardware test suite before each commit. Fix regressions before continuing.
- **R16 Report honestly.** In the Progress Log, list what was NOT done, known issues, and anything not verified. Never claim success that was not demonstrated.

### 0.3 Standard Definition of Done (applies to every stage; each stage adds its own items)
- All stage tasks complete; every acceptance criterion demonstrated (show command output, logs or screenshots).
- Required tests written and passing: `uv run pytest` (core), `pnpm test` (UI / extension), `cargo test` (shell), as applicable.
- Lint and type checks clean: `ruff check`, `ruff format --check`, `mypy`, `eslint`, `tsc --noEmit`, `cargo clippy -- -D warnings`, as applicable.
- No secrets in the diff. No new TODO without a note in the Progress Log.
- All [VERIFY] items of the stage resolved and recorded.
- Doc updated: STATUS (current/last stage), Progress Log entry, any spec changes, Decision Log changes (with Sharan's approval).
- Committed with the `[Sxx]` prefix. Sharan approved moving to the next stage.

### 0.4 ID and tag legend

| Prefix / tag | Meaning |
|---|---|
| `FR-<AREA>-<n>` | Functional requirement (§3.1) |
| `NFR-<n>` | Non-functional requirement (§3.2) |
| `D-<nn>` | Decision (§4) |
| `S<nn>` | Build stage (§18) |
| `M<n>` | Milestone (§18.1) |
| `SC-<nn>` | Canonical scenario (§2.2) |
| `R-<n>` | Risk (§20) |
| `PL-<nnnn>` | Progress Log entry (§23) |
| `T0`–`T3` | Permission tiers (§15.3) |
| [MUST] / [SHOULD] / [MAY] | Requirement strength (RFC 2119 meaning) |
| [VERIFY] | Volatile external fact. Confirm against an official source before relying on it |
| [USER-ACTION] | Something only Sharan can do (accounts, installs, recordings, approvals) |

### 0.5 How Sharan uses this doc
1. Open a new AI coding session in `E:\A.C.E` and paste the prompt from §0.6.
2. The AI works on the current stage only and ends with a Progress Log entry plus a summary.
3. Sharan reviews the result (try the acceptance criteria yourself), then says "approved, next stage" or asks for fixes.
4. The AI updates STATUS to the next stage and commits.

### 0.6 Session-start prompt (copy-paste for any AI)
```
You are a senior engineer building ACE in E:\A.C.E. Read ACE_MASTER_PLAN.md: STATUS, all of §0,
§4, the current stage in §18 with its linked sections, and the last 3 entries of §23.
Then tell me: the current stage, your plan for this session, and the [VERIFY] items you will check.
Follow the §0.2 rules strictly. Do not start the next stage without my approval.
```

---

## §1 Vision & principles

### 1.1 One-liner
ACE is a voice-and-text **operator** for Windows. It does things on Sharan's PC: it opens and controls apps, browser tabs, AI websites, music, messages, files and alarms. It verifies its own work, asks when unsure, and remembers Sharan's preferences compactly.

### 1.2 ACE is / ACE is not

| ACE IS | ACE IS NOT |
|---|---|
| An operator that uses the best tool per job (Gemini for images, Claude for code, Spotify for music…) | Another general chatbot competing with Gemini / Claude / ChatGPT |
| A real Windows desktop app: tray, always-on-top HUD, alive in the background | A web app or a browser tab |
| Free and open source (Apache-2.0) | Dependent on any paid API or service |
| Tailored to a student + software engineer | A do-everything business suite (no accounting, CRM, etc.) |
| Careful: verifies every action, confirms irreversible ones, asks when unsure | Autonomous in risky situations |
| Lightweight, with a 2D JARVIS-style HUD | Heavy, with 3D models |

### 1.3 Principles (ordered; when two conflict, the earlier one wins)
- **P1 Safety & honesty.** No irreversible action without confirmation. Never pretend success. Say "I'm not sure" and ask.
- **P2 Functionality first.** Features must work reliably before they look polished. (Security basics are still non-negotiable from day 1 — D-19.)
- **P3 Verify everything.** Every action is checked (§9).
- **P4 Local-first & private.** Audio never leaves the PC. Secrets stay in the OS vault. No telemetry.
- **P5 Free forever.** Every required component costs ₹0. Paid things are only optional bring-your-own.
- **P6 Lightweight.** No 3D, no heavy frameworks without reason. Idle cost near zero.
- **P7 Fast.** Simple commands feel instant (NFR-1).
- **P8 Personal.** Learns preferences compactly. Talks like a chill friend.
- **P9 Replaceable parts.** Every engine (STT, TTS, LLM, provider, site adapter) sits behind an interface and can be swapped.

---

## §2 User persona & canonical scenarios

### 2.1 Persona
- **Sharan** — student and software engineer. Codes in VS Code. Wants to be addressed as "Sharan" or "boss".
- Uses **Google Chrome** (one profile, several Google accounts via the account switcher). Default browser on the dev PC is Edge, but Chrome is the one ACE drives.
- **Spotify Premium** (Microsoft Store app), **WhatsApp Desktop**, Instagram / YouTube / Gmail on the web.
- AI subscriptions: **Google AI Pro (student)** for Gemini, **Claude Pro/Max**, plus ChatGPT.
- Speaks **English with Hinglish mixing**. ACE replies in English.
- Games on the same laptop.

**Dev machine baseline (detected 2026-11-06):** ASUS ROG Strix G16 (G614JU), Intel i7-13650HX (14 cores / 20 threads), NVIDIA RTX 4050 Laptop 6 GB VRAM + Intel UHD, 16 GB RAM, 1920×1200, Realtek laptop speakers + microphone array, Windows 11 26H2 (build 26300). Installed: Python 3.12.10 (+3.14 via `py`), Node 26.13, git 2.56, uv 0.13.6, VS Code. Not installed: Rust, MS C++ Build Tools, .NET SDK, pnpm. Free disk at detection: C: 14 GB, D: 2 GB, E: 22 GB.

**Portability:** ACE must also run on other Windows 11 PCs, including PCs without an NVIDIA GPU (CPU fallbacks, §7.8).

### 2.2 Canonical scenarios (milestone acceptance tests)

| ID | Trigger | Expected behavior | Stages |
|---|---|---|---|
| SC-01 | Types "open spotify" in the sidebar | Spotify (Store app) opens or comes to front within 1.5 s. Rule check confirms the window. Sidebar shows ✓. | S07, S08 |
| SC-02 | "Hey Ace" … "open VS Code" | Wake chime, VS Code opens, ACE says a short line like "Opening VS Code." | S13 |
| SC-03 | "Hey Ace, play lo-fi beats on Spotify" | Spotify search → plays the best match → verified via playback state → "Lo-fi it is, boss." | S21 |
| SC-04 | "next song" / "volume to 30" / "pause" | Works in normal mode and in game mode. | S19, S21, S36 |
| SC-05 | "make an image of a neon Mumbai street at night" | Preference → Gemini on the student account → background tab → prompt → wait → image saved to `Pictures\ACE\` → toast + voice + phone push "Your image is ready, boss." | S26, S31, S37 |
| SC-06 | Selects an error in a terminal: "Hey Ace, ask Claude how to fix this" | Selected text captured → new claude.ai chat with error + question → notifies when the answer is complete → "show me" brings the tab forward. | S23, S26 |
| SC-07 | "what's 18 percent of 2450" / "explain Raft consensus in depth" | Quick: ACE answers immediately ("441"). Deep: delegated to the preferred AI site, notify when ready. | S16, S26 |
| SC-08 | "wake me at 6:30 tomorrow" | "Alarm set for 6:30 AM tomorrow, Friday." At that time: sound + voice + toast + phone push. "snooze 10" works. | S20, S37 |
| SC-09 | "set a 25 minute timer" | Countdown visible in sidebar, rings at the end. | S20 |
| SC-10 | "any new WhatsApp messages?" → "reply to Mom: I'll be home by 8" | Summary of unread chats. Shows exact text → "Send it?" → "yes" → sent; council verifies the message bubble. | S29 |
| SC-11 | "summarize unread emails on my college account" | Routes to the mapped Google account, verifies the account on the page, summarizes. | S28 |
| SC-12 | "open my Instagram DMs and read the latest" | Summary; draft reply → confirm → send. | S30 |
| SC-13 | "play the latest Fireship video on YouTube" | Search → plays → "next video" works. | S27 |
| SC-14 | "study mode" | Routine: VS Code with last project, Spotify lo-fi, Do-Not-Disturb (if supported), 50-min focus timer. | S32 |
| SC-15 | "open the ACE project and run the tests" | VS Code opens the folder; tests run (confirmation or pre-approved command) → "142 passed, 2 failed — want me to send the failures to Claude?" | S33 |
| SC-16 | "Hey Ace, dictate" | Everything said is typed into the focused field until "stop dictation". | S35 |
| SC-17 | Launches a game | Overlay hides within 2 s, GPU models unload, "Hey Ace, next song" still works; everything restores after the game closes. | S36 |
| SC-18 | "open the project" (2 candidates) | "Which one — ACE or Portfolio?" → answer → proceeds. | S16 |
| SC-19 | Gemini tab shows a sign-in page mid-task | Council detects it. ACE pauses: "Gemini wants you to sign in to your student account. Tell me when you're done." → resumes. | S18, S25 |
| SC-20 | "delete everything in Downloads older than a month" | ACE lists the count and size → "Move 312 files (4.1 GB) to the Recycle Bin?" → acts only after "yes". | S22 |
| SC-21 | Chooses Gemini for image edits twice | ACE asks once: "Want me to always use Gemini for image edits?" → yes → next "edit this image" goes straight to Gemini. | S31 |
| SC-22 | Wi-Fi off | "open Spotify", "set a timer", "volume up" still work (local fast path). ACE says AI sites are unavailable when asked. | S16, S41 |
| SC-23 | "Hey Ace, paranoid mode" | Confirms; the council now checks every step with 3 verifiers; the mode chip shows "Paranoid". | S18 |
| SC-24 | "what's on my screen?" | Local OCR / UI Automation summary. Cloud vision only when Sharan says "look at my screen". | S23 |


---

## §3 Requirements

### 3.1 Functional requirements

| ID | Requirement | Strength | Stages |
|---|---|---|---|
| FR-CORE-1 | ACE runs as a per-user background app (tray). It can start with Windows (user toggle) and keeps working when all its windows are hidden or minimized. | MUST | S04, S13 |
| FR-CORE-2 | Single instance: launching again focuses the running instance. | MUST | S04 |
| FR-CORE-3 | The core process is supervised: auto-restart on crash; the UI shows connection state. | MUST | S04, S41 |
| FR-CORE-4 | An emergency-stop hotkey and the voice command "stop" cancel all running actions immediately and release any held keys or mouse buttons. | MUST | S17 |
| FR-CORE-5 | Portable mode, plus export/import of the profile (settings + memory) to move to another PC. | SHOULD | S44 |
| FR-IN-1 | Wake phrase "Hey Ace". | MUST | S12 |
| FR-IN-2 | Push-to-talk hotkey and summon/type hotkey. | MUST | S04, S13 |
| FR-IN-3 | Typed commands (sidebar / Control Center) use the same pipeline as voice. | MUST | S07 |
| FR-IN-4 | Understands English and Hinglish (mixed Hindi/English, romanized). | MUST | S10, S16 |
| FR-IN-5 | Follow-up window: after a reply, listens about 8 s without needing the wake phrase. | SHOULD | S13 |
| FR-IN-6 | Dictation mode types speech into the focused app. | MUST | S35 |
| FR-OUT-1 | Human-like British male voice, final voice chosen by Sharan in an audition. | MUST | S11 |
| FR-OUT-2 | Short spoken replies; full detail in the sidebar. | MUST | S11, S16 |
| FR-OUT-3 | Notifications via toast + voice + sidebar, plus phone push. | MUST | S37 |
| FR-OUT-4 | Persona "chill friend"; addresses Sharan as "Sharan" or "boss". | MUST | S11 |
| FR-UI-1 | Always-on-top overlay (edge orb + slide-out sidebar) above all windows except games. Never steals focus unless summoned. Clicks pass through outside its own area. | MUST | S06 |
| FR-UI-2 | Sidebar shows: state, online/offline, health of providers / Chrome bridge / mic, live transcript, task progress with verification badges, background jobs, text box, mode controls. | MUST | S06, S13, S18 |
| FR-UI-3 | Control Center window: history, memory, routines, skills & permissions, accounts & contacts, providers & keys, voice, devices, browser bridge, games, notifications, appearance, diagnostics, about/updates. | MUST | S05, S42 |
| FR-UI-4 | JARVIS HUD visual style, 2D only. | MUST | S05 |
| FR-UI-5 | Alternative overlay skins (top-center pill, always-visible slim bar), shipped only if they pass the stability gate. | MAY | S39 |
| FR-BR-1 | Fast path for common commands that needs no cloud call. | MUST | S07, S16 |
| FR-BR-2 | LLM planner with tool calling for complex commands; hybrid local + free-cloud provider pool with failover and quota tracking. | MUST | S14, S15, S16 |
| FR-BR-3 | Clarifying questions when a command is ambiguous, low-confidence or missing information. | MUST | S16 |
| FR-BR-4 | General questions: quick ones answered by ACE; deep ones delegated to the preferred AI site (D-11). | MUST | S16, S26 |
| FR-BR-5 | Multi-step tasks with progress, cancellation and background execution. | MUST | S17 |
| FR-VER-1 | Verification council with Fast / Balanced / Paranoid modes, switchable by voice. | MUST | S18 |
| FR-VER-2 | Takeover on failure; at most 2 takeovers per task, then ask Sharan. | MUST | S18 |
| FR-VER-3 | Verification results visible in the UI and stored in the audit log. | MUST | S18 |
| FR-SEC-1 | Permission tiers T0–T3: T2 always confirms, T3 never runs. | MUST | S07, S43 |
| FR-SEC-2 | Per-task capability scoping (a task can only use the skills its command implies). | MUST | S17 |
| FR-SEC-3 | Untrusted-content (prompt-injection) policy for web, screen, file and message content. | MUST | S16, S24, S43 |
| FR-SK-APP-1 | Launch / focus / close / minimize / maximize / snap / switch apps and windows, including Microsoft Store apps. | MUST | S08 |
| FR-SK-SYS-1 | Volume, media keys + now playing, brightness, Wi-Fi / Bluetooth, lock / sleep / restart / shutdown, screenshots, clipboard, battery, open Settings pages. | MUST | S19 |
| FR-SK-ALM-1 | Alarms, timers and reminders with persistence and snooze. | MUST | S20 |
| FR-SK-SPOT-1 | Spotify search / play / pause / next / queue / like / playlists via the Web API, with media-controls fallback. | MUST | S21 |
| FR-SK-FILE-1 | Find / open / move / copy / rename files; delete only to the Recycle Bin, with confirmation. | MUST | S22 |
| FR-SK-SCR-1 | Read screen text (OCR / UI Automation), capture selected text, "explain this", cloud vision only on explicit request. | MUST | S23 |
| FR-SK-WEB-1 | Chrome tab control: list, open, switch, close, search tabs; read page text. | MUST | S24 |
| FR-SK-AI-1 | Operate Gemini (text, image generate / edit), Claude, ChatGPT: prompt, wait, extract, save, notify. | MUST | S25, S26 |
| FR-SK-YT-1 | YouTube search, play and control. | MUST | S27 |
| FR-SK-MAIL-1 | Gmail with multiple accounts: read / summarize / search / draft / send (confirm). | MUST | S28 |
| FR-SK-WA-1 | WhatsApp Desktop: read / summarize / draft / send (confirm) / open chat. | MUST | S29 |
| FR-SK-IG-1 | Instagram web: DMs read / summarize / draft / send (confirm); open profiles and reels. | MUST | S30 |
| FR-SK-ROUT-1 | Routines: one phrase (or time / event) runs many actions. | MUST | S32 |
| FR-SK-DEV-1 | Developer tools pack (VS Code, terminal, git, run/test, send errors to Claude, GitHub pages). | MUST | S33 |
| FR-SK-STUDY-1 | Study tools pack (focus timer, notes, to-dos, course links, summarize files via AI sites). | MUST | S34 |
| FR-MEM-1 | Preferences (e.g. images → Gemini) are applied automatically. | MUST | S31 |
| FR-MEM-2 | Learning by suggest-and-confirm, plus explicit "remember" / "forget". | MUST | S31 |
| FR-MEM-3 | Compact memory with hard budgets and compaction. | MUST | S31 |
| FR-MEM-4 | Memory can be viewed, edited and deleted in the UI. | MUST | S31 |
| FR-CTX-1 | Game mode: hide overlay, free the GPU, voice-only subset (D-15). | MUST | S36 |
| FR-CTX-2 | Phone push notifications via ntfy. | MUST | S37 |
| FR-CTX-3 | MCP: ACE as MCP client and as MCP server. | SHOULD | S38 |
| FR-DIST-1 | Per-user installer, portable zip and signed auto-update. | MUST | S44 |
| FR-DIST-2 | Public open-source repository with license, docs and third-party notices. | MUST | S45 |

### 3.2 Non-functional requirements (initial targets; re-measured and refined at S40)

| ID | Requirement |
|---|---|
| NFR-1 Latency (dev machine) | Wake phrase end → chime ≤ 300 ms. End of speech → final transcript ≤ 700 ms (utterance ≤ 5 s). Transcript → fast-path action started ≤ 300 ms. End of speech → visible action for a simple command ≤ 1.5 s. Reply text → first TTS audio ≤ 500 ms. Hotkey → overlay visible ≤ 150 ms. |
| NFR-2 Resources | Idle (wake word listening, overlay collapsed): CPU ≤ 3 % average, RAM ≤ 1.2 GB for all ACE processes (excluding VRAM), no running animations. VRAM ≤ 5.0 GB in normal mode, ≤ 0.3 GB in game mode. Installed app ≤ 300 MB excluding models; default model set ≤ 8 GB. |
| NFR-3 Reliability | Core crash → auto-restart ≤ 3 s. No DB corruption on power loss (SQLite WAL). Interrupted tasks are reported, never blindly resumed. ≥ 99 % success on the text golden command set at M5. |
| NFR-4 Accuracy | Wake word ≥ 95 % detection at about 1 m in a quiet room; ≤ 1 false wake per 8 h of mixed media audio. STT word error rate ≤ 10 % on Sharan's English set and ≤ 15 % on Sharan's Hinglish set (confirmed at S10). |
| NFR-5 Privacy | Audio processed locally only. Transcripts stored as text only. Screenshots not stored unless Sharan saves one. Zero telemetry. All data local. |
| NFR-6 Security | §15 baseline from S01; full hardening at S43. |
| NFR-7 Portability | Windows 11 x64 (23H2 or newer); Windows 10 22H2 best-effort. Runs without an NVIDIA GPU (CPU fallbacks). No admin rights needed to install or run. |
| NFR-8 Licensing | All shipped components are permissively licensed and compatible with Apache-2.0 (§6.4). No non-commercial ("NC") model weights shipped. Third-party notices maintained. |
| NFR-9 Maintainability | Typed code: mypy strict for `ace_core`, TypeScript strict. ruff / eslint / clippy clean. Unit-test coverage ≥ 80 % for non-hardware core logic. |
| NFR-10 Accessibility | Control Center fully keyboard-navigable. `prefers-reduced-motion` honored. Text contrast meets WCAG AA. |
| NFR-11 Cost | ₹0 required. Optional, never required: Chrome Web Store developer fee, OpenRouter credit top-up, paid code signing if no free program is available. |

### 3.3 Traceability — Sharan's original requests → requirements → stages

| # | Sharan asked for | Covered by | Stages |
|---|---|---|---|
| 1 | An operator, not another chatbot; use the best AI per task | FR-SK-AI-1, FR-MEM-1, FR-BR-4, §1.2 | S16, S26, S31 |
| 2 | Wake it up by voice | FR-IN-1 | S12 |
| 3 | "Open Spotify", "play a song" | FR-SK-APP-1, FR-SK-SPOT-1 | S08, S21 |
| 4 | "Go to another tab, open Claude, ask it something" | FR-SK-WEB-1, FR-SK-AI-1 | S24, S26 |
| 5 | Set alarms | FR-SK-ALM-1 | S20 |
| 6 | Type prompts into Claude / Gemini, make images, tell me when done | FR-SK-AI-1, FR-OUT-3 | S26, S37 |
| 7 | A proper software app, Windows only, portable to other PCs | FR-CORE-1, FR-CORE-5, FR-DIST-1, NFR-7 | S04, S44 |
| 8 | Full PC access is fine | §15.3 tiers (access granted, irreversible actions still confirmed per D-10) | S07 |
| 9 | Very fancy front end, no 3D, not heavy | FR-UI-4, NFR-2 | S05, S40 |
| 10 | Excellent backend and database; skip nothing | §13, NFR-3, NFR-9 | S02, S41 |
| 11 | System design + security incl. SQL injection (full pass last) | §15, D-19 | S02, S03, S43 |
| 12 | Free and open source | NFR-8, NFR-11, FR-DIST-2 | S45 |
| 13 | A good, human-sounding free voice | FR-OUT-1 | S11 |
| 14 | Tailored to a student / SWE; no unnecessary features | FR-SK-DEV-1, FR-SK-STUDY-1, §1.2 | S33, S34 |
| 15 | Overlay on top of everything except games; works minimized; shows online/offline and the interaction log | FR-UI-1, FR-UI-2, FR-CORE-1, FR-CTX-1 | S06, S36 |
| 16 | Speak everything, but typing works too | FR-IN-3 | S07, S13 |
| 17 | Ask back when there is a problem (anti-hallucination) | FR-BR-3, §9.5 | S16, S18 |
| 18 | Save preferences ("edit image" → Gemini) | FR-MEM-1, FR-MEM-2 | S31 |
| 19 | Compact memory that can't bloat or crash it | FR-MEM-3 | S31 |
| 20 | 2–3 AIs verifying live; they take over when it goes wrong | FR-VER-1, FR-VER-2 | S18 |
| 21 | Many small stages; the AI builder must know what happened | §0, §18, §23 | all |
| 22 | WhatsApp, Instagram, Gmail, YouTube (Q&A round 2) | FR-SK-WA-1, FR-SK-IG-1, FR-SK-MAIL-1, FR-SK-YT-1 | S27–S30 |
| 23 | Routines, dictation, phone notifications, MCP (Q&A round 5) | FR-SK-ROUT-1, FR-IN-6, FR-CTX-2, FR-CTX-3 | S32, S35, S37, S38 |

---

## §4 Decision Log

Status values: **Decided** = confirmed by Sharan in the 2026-11-06 Q&A. **Default** = chosen by the developer; Sharan may veto at any time. **Engineering** = technical choice by the developer, changeable via R2.

| ID | Decision | Status | Rationale / notes |
|---|---|---|---|
| D-01 | Speech input: English + Hinglish. ACE replies in English. STT = Whisper family (baseline: faster-whisper `large-v3-turbo`); the final model is picked at S10 by benchmarking on Sharan's own recordings. | Decided | Parakeet is faster but does not cover Hindi; Whisper does. |
| D-02 | Wake phrase "Hey Ace" (custom-trained free model) + hotkeys. | Decided | Two-word phrases trigger by accident far less than "Ace". |
| D-03 | Voice: British male, JARVIS feel. Audition Kokoro British male voices vs Chatterbox-Turbo with a CC-BY British reference (e.g. VCTK). Never clone a real public figure's voice. | Decided | Best free human-like quality; legally clean. |
| D-04 | Persona "chill friend". Address: "Sharan" / "boss". Short spoken replies, details in the sidebar. | Decided | |
| D-05 | Brain = Hybrid. Simple commands: rules + local LLM (llama.cpp, ~4B, GPU). Complex: free cloud provider pool with quota tracking and failover. Audio never leaves the PC. | Decided | Free tiers are volatile (GitHub Models retired 2026-07-30; Gemini free tier is Flash / Flash-Lite only). |
| D-06 | Operated services: Gemini, Claude, ChatGPT, YouTube, Gmail, Instagram (web, in Chrome); WhatsApp (desktop app); Spotify (Premium → official Web API with PKCE and an `http://127.0.0.1` loopback redirect; media-controls fallback). | Decided | Spotify Dev Mode requires the owner to have Premium (since Feb 2026) — Sharan has it. |
| D-07 | ToS approach: free official APIs for ACE's own thinking; driving websites for subscription features is opt-in per site, with a warning, at human pace, only on Sharan's command. | Decided | Automating consumer sites is a ToS gray area (R-1). |
| D-08 | Accounts: Spotify Premium, Google AI Pro (student), Claude Pro/Max. One Chrome profile with several Google accounts. ACE keeps a service → account map, routes via Google's `authuser` / `/u/N/` URLs, and verifies the active account on the page before acting. | Decided | "Gmail accounts can differ" (Sharan). |
| D-09 | Verification modes Fast / **Balanced (default)** / Paranoid, switchable by voice (§9). | Decided | |
| D-10 | Confirmation for irreversible actions (T2): sends, deletes (Recycle Bin only), git push, running scripts / commands, shutdown / restart, purchases. Forbidden (T3): typing passwords / OTPs / payment data, solving CAPTCHAs, permanent delete, bulk messaging, financial transfers, disabling security software, `git push --force` and other destructive shell commands. | Decided | |
| D-11 | General questions: quick ones answered by ACE; deep ones (explanations, code, research) delegated to the preferred AI site, with a notification when ready. | Decided | |
| D-12 | Messaging (WhatsApp, Instagram, Gmail): read & summarize, draft, send by voice (with confirmation), open / navigate. | Decided | |
| D-13 | Overlay: Edge orb + slide-out sidebar first. Top-center pill and slim bar become switchable skins only if they pass the S39 stability gate; otherwise they are dropped. | Decided | "If it crashes, do only the recommended one" (Sharan). |
| D-14 | Visual style: JARVIS HUD (dark, cyan glow, 2D CSS/SVG rings + waveform). No 3D / WebGL. Animations stop when idle or hidden. | Decided | |
| D-15 | Game mode: hide overlay, unload GPU models, voice-only subset (music, volume, timers, alarms, time). | Decided | |
| D-16 | Skill packs: Developer tools, Study tools, Screen understanding, Files & folders (all), plus the core packs. | Decided | |
| D-17 | Extras: Routines, Dictation anywhere, Phone push (ntfy), MCP (client: Windows on-device agent connectors + community servers; server: expose ACE skills to Claude Code). | Decided | |
| D-18 | Stack: Tauri 2 (thin Rust shell) + React / TypeScript / Vite UI + Python 3.12 core (uv). Chrome MV3 extension + Native Messaging for browser control. | Decided | Lightest final app; best free AI / voice / Windows-automation libraries are in Python; Chrome 136+ ignores remote debugging on the default profile. |
| D-19 | Security: secure basics from day 1 (§15.1); full hardening pass at the end (S43). | Decided | Retrofitting basics later forces rewrites. |
| D-20 | Documentation: this single Markdown file. | Decided | Best for AI parsing, editing and git history. |
| D-21 | License: Apache-2.0. | Default | Permissive with a patent grant. |
| D-22 | Distribution: per-user installer (no admin) + portable zip + profile export / import (`.acepack`). | Default | |
| D-23 | Memory learning: suggest-and-confirm plus explicit "remember" / "forget". | Default | |
| D-24 | Browser tasks run in a background tab and notify when done; "show me" brings the tab forward. Explicit "open / go to …" commands act in the foreground. | Default | Sharan can keep working while ACE operates. |
| D-25 | Build order: text-command spine first, then voice, brain, skills, web apps, personal layer, hardening. | Default | Voice is an I/O layer over the same pipeline. |
| D-26 | Retention: raw messages 30 days (then compacted into summaries); audit log 90 days; verifications 30 days; tasks 90 days; transcripts stored as text only; no audio stored. | Default | |
| D-27 | Zero telemetry. | Default | |
| D-28 | Browser support: Chrome only for v1 (the extension is Chromium-compatible; Edge / Brave later). | Default | Sharan uses Chrome. |
| D-29 | Hotkeys (configurable; conflicts checked at S04): `Ctrl+Alt+Space` summon sidebar + focus input · hold `Ctrl+Alt+A` push-to-talk · `Ctrl+Alt+Esc` emergency stop · `Ctrl+Alt+H` hide/show overlay · `Ctrl+Alt+M` mic mute. | Default | Avoids `Ctrl+Space` (VS Code suggestions) and `Alt+Space` (window menu / PowerToys). |
| D-30 | Cloud vision only on an explicit "look at my screen"-type request; otherwise local OCR / UI Automation. | Default | Privacy. |
| D-31 | Database: SQLite (WAL, FTS5) + SQLAlchemy 2 + Alembic. Secrets in Windows Credential Manager via `keyring`. | Default | Right fit for a single-user local app; no server to run. |
| D-32 | Local LLM runtime: llama.cpp `llama-server` (OpenAI-compatible API) managed by ACE. Ollama / LM Studio supported as optional external providers. | Engineering | Self-contained, no extra install for users. |
| D-33 | IPC: FastAPI (REST + WebSocket) on `127.0.0.1`, random port, per-run token, Origin allowlist. Pydantic models are the schema source of truth → generated TypeScript types. | Engineering | One schema, no UI/core drift. |
| D-34 | Python 3.12 (not 3.14) for ML wheel compatibility; uv for environments and lockfile. | Engineering | |
| D-35 | pnpm for JavaScript packages (disk-efficient shared store on E:). | Engineering | Disk is tight. |
| D-36 | TTS default until the S11 audition: Kokoro-82M on CPU (`kokoro-onnx`). | Engineering | Fast, light, frees VRAM. |
| D-37 | STT baseline: faster-whisper `large-v3-turbo` on CUDA (int8_float16) with CPU fallback; final choice by the S10 benchmark. | Engineering | |
| D-38 | Contacts: ACE keeps its own local contact book (name, aliases, WhatsApp number, Instagram handle, emails). Never synced or uploaded. | Engineering | Needed for "tell Mom…". |
| D-39 | Phone push: ntfy (public ntfy.sh server by default, with a long random secret topic; self-hosting optional). Push content is minimal (no message bodies). | Engineering | Free and open source. |
| D-40 | Overlay click-through: the Rust shell polls the cursor position (~60 Hz) and toggles ignore-cursor-events when the cursor is over the orb/sidebar hit-area [VERIFY at S06]. | Engineering | Tauri has no "forward mouse events" option like Electron. |
| D-41 | App identifier: `io.github.quirky-sharan.ace` (Windows app-data folder, notifications). Changing it later moves user data. | Decided | Chosen by Sharan at S00 (2026-11-06). |
| D-42 | Build toolchain, all on E: (§17.4): VS 2022 Build Tools (MSVC v143) + standalone Windows 11 SDK 10.0.26100; Rust stable via rustup (minimal profile + rustfmt + clippy); pnpm 12 installed with npm; uv-managed CPython 3.12. Exact versions in PL-0002. | Engineering | rustup's MSVC docs cover VS 2022 (2026 not yet documented); Sharan asked for everything on E:. |
| D-43 | Workspace layout: one pnpm workspace (`apps/*`, single `pnpm-lock.yaml`); the Python core is its own uv project in `core/`; shared ESLint flat config (`defineConfig`) + Prettier at the repo root; Markdown is excluded from Prettier. | Engineering | One lockfile per ecosystem; the master plan is never reflowed. |
| D-44 | Quality gates: pre-commit (pre-commit-hooks, ruff, detect-secrets with `.secrets.baseline`, local mypy / eslint / prettier / cargo fmt / clippy hooks); CI on `windows-latest` with GitHub Actions pinned to exact release tags. | Engineering | §16.7; exact tags are reproducible (SHA pinning reviewed at S43). |

---

## §5 Architecture

### 5.1 Process view

```
┌──────────────────────────────────── Windows user session ─────────────────────────────────────┐
│                                                                                                │
│  ace-desktop.exe  (Tauri 2 / Rust)                          Chrome (Sharan's profile)          │
│  ├─ tray, global hotkeys, autostart, updater                ├─ ACE Bridge extension (MV3)       │
│  ├─ windows: orb + sidebar (overlay), Control Center        │   service worker + content scripts│
│  │   └─ WebView2 → React UI ───────────┐                    └───────────────┬───────────────────┘
│  └─ supervisor: spawns / restarts      │ WebSocket (token)                  │ Native Messaging (stdio)
│     ace-core                           ▼                                    ▼
│  ace-core.exe  (Python 3.12, asyncio) ◄──── WebSocket (token) ────── ace-core (native-host mode)
│  ├─ IPC server (FastAPI, 127.0.0.1:<random>)                                                   │
│  ├─ voice: mic → VAD → wake word → STT  │  TTS → speakers  │  dictation                         │
│  ├─ brain: router (fast/slow) → agent runtime → verification council → skills                  │
│  ├─ skills: apps, windows, system, media, spotify, alarms, files, screen, browser, AI sites,    │
│  │          youtube, gmail, whatsapp, instagram, dev, study, routines, notify, mcp               │
│  ├─ memory + SQLite DB (%LOCALAPPDATA%\ACE\data\ace.db)                                         │
│  ├─ model manager → llama-server.exe (local LLM, CUDA) + STT/TTS/wake/VAD models               │
│  └─ provider pool → Gemini / Groq / OpenRouter / Cerebras / Mistral (HTTPS, free tiers)        │
└────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 5.2 Components

| Component | Language | Responsibilities | Never does |
|---|---|---|---|
| ace-desktop (shell) | Rust (Tauri 2) | Tray, single instance, global hotkeys, autostart, updater, window management (overlay + Control Center), click-through polling, supervising ace-core | Business logic, AI, DB access |
| ace-ui | React + TypeScript | Overlay (orb, sidebar, skins), Control Center pages, HUD design system, IPC client | Direct OS access; storing secrets |
| ace-core | Python 3.12 | Voice, brain, council, skills, memory, DB, model manager, provider pool, IPC server, native-messaging host mode | UI rendering |
| ace-bridge | TypeScript (Chrome MV3) | Tab operations, DOM reading/acting, site adapters, downloads | Deciding what to do (core decides); keeping secrets |
| llama-server | C++ (llama.cpp binary) | Local LLM inference via an OpenAI-compatible HTTP API on 127.0.0.1 | Anything else |

### 5.3 Data flow of a voice command
1. Mic frames (16 kHz mono) → ring buffer (2 s pre-roll).
2. The wake detector runs continuously on CPU. When "hey ace" scores ≥ threshold → state LISTENING, chime, overlay opens.
3. VAD segments speech until ~700 ms of silence (or 15 s max).
4. STT → text + confidence.
5. Router: fast path (grammar + fuzzy matching) → if confident, a one-step task. Otherwise slow path: local LLM classifier, then cloud planner with tool schemas + memory context (§8.1).
6. Supervisor: permission tier + capability scope → confirmation request if T2, refusal if T3.
7. Agent runtime executes steps; the council verifies each one (§9).
8. Response composer: a short spoken line (TTS) + a detailed sidebar entry; notifications for background tasks.
9. Everything is logged: messages, tasks, steps, verifications, audit.

Typed commands enter at step 5 with the same pipeline.

### 5.4 State machines

**Conversation state** (one at a time; drives the orb):

| State | Meaning | Orb visual |
|---|---|---|
| ASLEEP | Only the wake word is active | dim cyan, slow breathe |
| LISTENING | Capturing a command | bright cyan pulse + live waveform |
| TRANSCRIBING | STT running | violet shimmer |
| THINKING | Routing / planning | violet rotating ring |
| ACTING | Executing foreground steps | amber progress ring |
| SPEAKING | TTS playing | cyan waveform from output level |
| AWAITING_CONFIRM | Waiting for yes/no on a T2 action | orange pulse + confirm card |
| AWAITING_ANSWER | Waiting for a clarification answer | orange pulse + options card |
| FOLLOW_UP | Listening ≤ 8 s without the wake word | cyan outline pulse |
| DICTATING | Dictation mode | green outline + "DICTATING" chip |
| MUTED | Microphone closed by Sharan | grey with slash |
| ERROR | Transient error being reported | red flash, then back to ASLEEP |

Flags (independent of the state): `game_mode`, `offline`, `dnd`, `paused_overlay`.

Main transitions: ASLEEP —wake/hotkey→ LISTENING —speech end→ TRANSCRIBING → THINKING → (ACTING | AWAITING_CONFIRM | AWAITING_ANSWER) → SPEAKING → FOLLOW_UP —timeout→ ASLEEP. From any state: "stop" / emergency hotkey → cancel → SPEAKING("Stopped.") → ASLEEP. Errors → ERROR → SPEAKING(short explanation) → ASLEEP.

**Task state** (each task independently; background tasks keep running while the conversation returns to ASLEEP): `queued → running → (waiting_user ↔ running) → verifying → succeeded | failed | cancelled | interrupted`.

### 5.5 IPC protocol (core ↔ UI, core ↔ native host, core ↔ dev CLI)
- **Transport:** WebSocket `ws://127.0.0.1:<port>/ws` for commands and events; REST `http://127.0.0.1:<port>/api/v1/...` for settings / CRUD. Bound to `127.0.0.1` only.
- **Auth:** per-run 256-bit random token. WebSocket: the first message must be `{"type":"auth","token":"…"}` within 2 s, or the connection is closed. REST: `Authorization: Bearer <token>`. Never put the token in a URL.
- **Origin allowlist:** the Tauri webview origin(s) [VERIFY the exact origin on Windows, e.g. `http://tauri.localhost`]. Connections without an Origin header are allowed only for the native host and the dev CLI (they still need the token).
- **Envelope:**
```json
{ "v": 1, "id": "01J…", "type": "request|response|event|error",
  "method": "command.submit", "params": {}, "result": {},
  "error": { "code": "E_AREA_NAME", "message": "human readable", "details": {} },
  "ts": "2026-11-06T10:00:00.000Z" }
```
- **Initial methods:** `system.health`, `system.state.get`, `command.submit`, `task.list`, `task.cancel`, `confirm.respond`, `clarify.respond`, `settings.get`, `settings.set`, `log.tail` (dev only). Later stages add `memory.*`, `routines.*`, `providers.*`, `voice.*`, `devices.*`, `overlay.*`, `accounts.*`, `contacts.*`, `models.*`, `bridge.*`.
- **Initial events:** `state.changed`, `transcript.partial`, `transcript.final`, `task.created`, `task.updated`, `task.step`, `task.verified`, `task.finished`, `confirm.requested`, `clarify.requested`, `notification.created`, `health.changed`, `audio.level`.
- **Schemas:** Pydantic v2 models in `core/src/ace_core/ipc/schemas.py` → JSON Schema → generated TypeScript in `apps/desktop/src/ipc/generated.ts` (script in `tools/`). CI fails if the generated file is stale.
- **Limits:** max message 1 MiB; per-connection rate limit; unknown method → `E_IPC_UNKNOWN_METHOD`.
- **Native messaging:** the extension talks to the ACE native host (the core executable launched by Chrome in native-host mode, §11.2) over stdio (Chrome framing: 4-byte little-endian length + UTF-8 JSON; host → extension max 1 MB per message [VERIFY]). The native host connects to the core WebSocket using port + token read from `%LOCALAPPDATA%\ACE\runtime\ipc.json` (file ACL: current user only).

### 5.6 Process lifecycle
1. ace-desktop starts (at login if autostart is on).
2. It generates a token and spawns ace-core with env `ACE_IPC_TOKEN=<token>` and `ACE_IPC_PORT=0`.
3. ace-core binds an ephemeral port, writes `runtime\ipc.json`, and prints `ACE_READY port=<port>` on stdout.
4. The shell gives port + token to its webviews through a Tauri command (never through the URL). The UI connects.
5. Core crash → the shell restarts it with backoff 1 s, 2 s, 4 s … max 30 s and shows a banner. After 5 crashes in 5 minutes → **safe mode** (voice off, minimal skills) and asks Sharan to open Diagnostics.
6. Quit: the shell asks the core to shut down gracefully (≤ 5 s), then kills it if needed. No orphan processes (use a Windows Job Object or an equivalent [VERIFY]).

### 5.7 Concurrency inside ace-core
- One asyncio event loop (Windows Proactor loop) for orchestration and IPC.
- Audio capture runs in the PortAudio callback thread → lock-free queue. Never run inference inside the callback.
- CPU/GPU-heavy inference (wake, STT, TTS) runs in worker threads or processes so the loop never blocks.
- COM / UI Automation calls run on one dedicated STA worker thread (COM apartment rules).
- Database writes go through a single-writer queue (§13.1).

### 5.8 Storage layout

```
%LOCALAPPDATA%\ACE\                 (portable mode: <app folder>\data\)
  data\ace.db  (+ -wal, -shm)
  data\backups\ace-YYYYMMDD.db      (7 kept + one before every migration)
  logs\core-YYYYMMDD.jsonl, desktop-YYYYMMDD.log   (14 days)
  runtime\ipc.json                  (port + token; ACL: current user only; deleted on exit)
  cache\
E:\ACE-Models\                      (configurable "models dir"; chosen at onboarding)
  stt\  tts\  wake\  vad\  llm\  bin\ (llama-server)  models.lock.json
%USERPROFILE%\Pictures\ACE\         (generated images, saved screenshots)
%USERPROFILE%\Documents\ACE\Notes\  (study notes exported as Markdown)
```

---

## §6 Tech stack

### 6.1 Components and libraries (exact versions are pinned at S00 / per stage and recorded in the Progress Log)

| Layer | Choice | License | Notes |
|---|---|---|---|
| Desktop shell | Tauri 2.x on Rust stable; plugins: single-instance, global-shortcut, autostart, updater, notification, shell / process | MIT / Apache-2.0 | [VERIFY] plugin names, APIs and the v2 capabilities/permissions format. Use v2 docs only. |
| UI | React + TypeScript (strict) + Vite + Tailwind CSS + Motion + Zustand + Radix primitives + lucide-react | MIT | Fonts bundled locally (no CDN): Orbitron or Rajdhani (HUD headings), Inter (body), JetBrains Mono (code) — all OFL [VERIFY]. |
| Core runtime | Python 3.12 via uv; FastAPI + Uvicorn; Pydantic v2 + pydantic-settings; SQLAlchemy 2 + Alembic; structlog; httpx; anyio | MIT / BSD | |
| Audio I/O | sounddevice (PortAudio) + numpy | MIT / BSD | |
| VAD | Silero VAD (ONNX) | MIT | |
| Wake word | openWakeWord-family runtime + custom-trained `hey_ace` model | Apache-2.0 (code) | Do NOT ship openWakeWord's pre-trained models (CC BY-NC-SA). [VERIFY] training pipeline and training-voice licenses. |
| STT | faster-whisper (CTranslate2) + Whisper `large-v3-turbo` | MIT | Needs CUDA 12 cuBLAS / cuDNN libraries on Windows [VERIFY]. |
| TTS | kokoro-onnx + Kokoro-82M weights (default); optional Chatterbox-Turbo (PyTorch CUDA) | Apache-2.0 / MIT [VERIFY] | Reference voice for Chatterbox from a CC-BY dataset (e.g. VCTK, CC BY 4.0) with attribution [VERIFY]. |
| Local LLM | llama.cpp `llama-server` + a GGUF ~4B instruct model with tool calling (Q4) | MIT + model license | [VERIFY] best current candidate (e.g. Qwen3-4B-Instruct class, Apache-2.0) at S14. |
| Cloud LLM clients | `openai` Python SDK for OpenAI-compatible endpoints; `google-genai` if needed for Gemini | Apache-2.0 | [VERIFY] each provider's endpoint at S15. |
| Windows integration | pywin32, comtypes, UI Automation library (`uiautomation` or pywinauto — decide at S08), pycaw, screen-brightness-control, psutil, mss, pywinrt packages (SMTC, OCR, Radios, notifications), send2trash, rapidfuzz, dateparser, keyring | various permissive | [VERIFY] package names and APIs per stage. |
| Browser bridge | Chrome MV3 extension in TypeScript, built with Vite; Chrome Native Messaging | MIT | |
| MCP | official MCP Python SDK | MIT [VERIFY] | |
| Testing | pytest, pytest-asyncio, hypothesis, pytest-cov; vitest + Testing Library; cargo test | MIT / BSD | |
| Quality | ruff, mypy, eslint, prettier, tsc, clippy, rustfmt, pre-commit; pip-audit, pnpm audit, cargo-audit, bandit, semgrep (S43) | permissive | |
| Packaging | Tauri bundler (NSIS, per-user); PyInstaller or Nuitka for the core (decide at S44); GitHub Actions; Tauri updater (signed) | permissive | |

### 6.2 Version policy
- At S00, choose the latest **stable** versions and record them in the Progress Log. Lockfiles (`uv.lock`, `pnpm-lock.yaml`, `Cargo.lock`) are committed.
- Never use open-ended "latest" ranges in manifests. Upgrades happen only in dedicated maintenance commits with tests.
- If an API differs from this doc for the pinned version, the pinned version's official docs win; update this doc (R10).

### 6.3 Why this stack (summary of D-18)
- **Tauri** gives a ~10–20 MB shell using Windows' built-in WebView2 → light (P6), yet full web tech for a rich HUD.
- **React / TypeScript** is what AI builders know best → fewer mistakes; huge ecosystem of accessible components.
- **Python** has the best free libraries for voice (faster-whisper, Kokoro, Silero, openWakeWord), LLM tooling and Windows automation (UI Automation, pywin32, WinRT).
- **Chrome extension + Native Messaging** is the only robust way to act inside Sharan's real, logged-in Chrome profile (Chrome 136+ ignores `--remote-debugging-port` on the default profile), and it can work in background tabs without moving the mouse.

### 6.4 License rules
- Project license: **Apache-2.0** (D-21).
- Allowed dependency licenses: MIT, BSD-2/3-Clause, Apache-2.0, ISC, Zlib, PSF, MPL-2.0 (file-level), CC-BY-4.0 (data / models, with attribution), OFL (fonts). LGPL only for dynamically linked libraries, and only if nothing else exists.
- Not allowed to ship: GPL / AGPL code (unless isolated as an optional separate download and approved by Sharan), any non-commercial ("NC") or "research-only" model weights, and anything with an unclear license.
- Every dependency and model is recorded (name, version, license, source URL) — as a list in Progress Log entries until S45, then in `THIRD_PARTY_NOTICES.md`.

---

## §7 Voice pipeline

### 7.1 Audio I/O
- WASAPI shared mode via `sounddevice`. Capture 16 kHz mono int16 (resample if the device can't). Frame size chosen to match the wake-word model's expected chunk (openWakeWord-style models use 80 ms = 1280 samples at 16 kHz [VERIFY]).
- Ring buffer keeps the last 2 s (pre-roll) so the command spoken right after "hey ace" is never cut.
- Playback via an output stream with a queue. Interrupt (stop) within 100 ms.
- [SHOULD] Duck other apps' volume while ACE speaks (pycaw), restore afterwards.
- Device selection is saved by device name, falling back to the Windows default. Handles hot-plug (e.g. a Bluetooth headset connecting).
- Mic mute = the capture stream is **closed** (the Windows mic-in-use indicator disappears), not just ignored.

### 7.2 Wake word ("Hey Ace")
- Interface: `WakeDetector.process(frame) -> float` (score 0–1).
- Model `hey_ace.onnx`, custom-trained at S12: synthetic positives from several free TTS voices (including Indian-English accents), speed/pitch/noise/reverb augmentation, plus Sharan's real recordings (≥ 50, [USER-ACTION]); negatives: normal speech, music, YouTube-like media, keyboard noise.
- Two-stage acceptance [SHOULD]: score ≥ τ_high → wake immediately. τ_low ≤ score < τ_high → quickly transcribe the last ~1.5 s and accept only if the text fuzzily contains "hey ace". Reduces false wakes without slowing normal wakes.
- Disabled while ACE is speaking (half-duplex, §7.7). Not needed during the FOLLOW_UP window.
- False-wake log stores only scores and timestamps (never audio) for tuning.

### 7.3 VAD
Silero VAD (ONNX). Initial parameters: speech threshold 0.5, minimum speech 250 ms, end-of-speech silence 700 ms (1,000 ms in dictation), maximum utterance 15 s (dictation streams in chunks). Tune at S10.

### 7.4 STT
- Interface: `Transcriber.transcribe(audio, hints) -> {text, segments, avg_logprob, no_speech_prob, language, duration_ms}`.
- Baseline (D-37): faster-whisper `large-v3-turbo` on CUDA, `compute_type="int8_float16"`, small beam (tune 1–5), no internal VAD (we already segment), no conditioning on previous text, temperature fallback off for latency. Vocabulary hint prompt: app names, contact names, "ACE", common Hinglish words [VERIFY parameter names for the pinned version].
- Candidates benchmarked at S10: (a) `large-v3-turbo`; (b) community Hinglish fine-tunes of Whisper (only with a permissive license [VERIFY]); (c) a smaller model for CPU fallback and game mode.
- Output: commands keep romanized Hinglish as spoken. If Devanagari appears, it is passed to the LLM as is (LLMs read both). Dictation output script is a user setting.
- Hallucination guards: drop the result if `no_speech_prob > 0.6` and `avg_logprob < -1.0` (tune); block-list of known phantom phrases ("thank you for watching", "subscribe", …); detect repetition loops.
- Low confidence → clarification ("Did you say 'open Spotify'?").
- Audio never leaves the PC (D-05). Cloud STT is not used.

### 7.5 TTS
- Interface: `Synthesizer.stream(text, voice, speed) -> AsyncIterator[pcm_chunk]`.
- Default: Kokoro-82M via `kokoro-onnx` on CPU (D-36). British male candidates: `bm_george`, `bm_lewis`, `bm_daniel`, `bm_fable` [VERIFY voice IDs].
- Optional: Chatterbox-Turbo on GPU with a reference clip of a CC-BY British male speaker (e.g. from VCTK) — attribution required. **Never clone a real public figure or anyone without consent** (no copying the movie JARVIS actor).
- Sentence-level chunking: start speaking after the first sentence is synthesized.
- Pronunciation lexicon (e.g. "ACE" → "Ace"; Sharan's name confirmed at S11 [USER-ACTION]).
- Interruptible within 100 ms (stop / hotkey / new wake).
- Earcons (short, subtle, generated or CC0): wake chime, done chime, error tone, confirm-prompt tone.

### 7.6 Persona & speech style (D-04)
- Chill friend with a British voice. Addresses Sharan as "Sharan" or "boss", alternating naturally — not in every sentence.
- Spoken replies ≤ 2 short sentences unless asked for more; details go to the sidebar.
- Light humor is fine, but never during errors, confirmations, warnings or bad news.
- Never says "As an AI…". Never invents results. Says plainly when something failed.

| Situation | Example spoken line |
|---|---|
| Simple success | "Spotify's up, boss." |
| Long task started | "On it — I'll ping you when Gemini's done." |
| Task done | "Your image is ready, Sharan. Want to see it?" |
| Confirmation (T2) | "Send this to Mom on WhatsApp: 'I'll be home by 8'?" |
| Clarification | "Which one — ACE or Portfolio?" |
| Failure | "Couldn't open that — Spotify isn't responding. Want me to try restarting it?" |
| Not sure | "I'm not sure I got that. Did you mean 'open Claude'?" |

### 7.7 Barge-in
- v1 (S13): **half-duplex**. While ACE speaks, the wake detector is off; interrupt with the emergency hotkey or the push-to-talk hotkey.
- S41: full-duplex barge-in using acoustic echo cancellation (WebRTC-style AEC via a maintained Python binding [VERIFY]) so "Hey Ace, stop" works over laptop speakers.

### 7.8 Model manager & hardware tiers
| Tier | Hardware | Defaults |
|---|---|---|
| A | NVIDIA GPU ≥ 6 GB (the dev laptop) | STT turbo on GPU; local LLM on GPU; TTS Kokoro on CPU (or Chatterbox on GPU if the budget allows); wake + VAD on CPU |
| B | NVIDIA 4 GB, other GPUs, or CPU-only with 16 GB RAM | STT smaller model on CPU (int8); no local LLM by default (cloud pool); Kokoro on CPU |
| C | 8 GB RAM, weak CPU | STT small / base on CPU; brain cloud-only; Kokoro on CPU |

- VRAM budget default **5.0 GB** of 6 GB. Priority: STT > local LLM > Chatterbox. Measured via NVML [VERIFY python binding].
- Lazy loading; unload the LLM after 30 min idle; unload all GPU models in game mode (STT falls back to the CPU model).
- Downloads only from official sources (Hugging Face model repos / GitHub releases) over HTTPS, verified against SHA-256 in `models.lock.json`, resumable, stored in the models dir on E:. Models are never bundled in the installer. Check free disk space before downloading.

---

## §8 Brain

### 8.1 Router (four stages)
1. **Normalize:** lowercase; strip fillers ("please", "can you", "zara", "na", "yaar"); expand memory aliases.
2. **Fast path (deterministic):** grammar patterns for the top intents — open / close / switch app, media (play / pause / next / previous / volume), simple timers and alarms, system toggles, "stop", mode switches, routine names, "dictate". Entities resolved with rapidfuzz against the app index, contacts and aliases. If the top-2 candidates are too close → clarification.
3. **Local LLM classifier** (≤ 4B, llama-server) for single-step commands the grammar missed → tool call JSON validated against the skill schema. [SHOULD]
4. **Cloud planner** (provider pool) for multi-step, complex or general questions → a plan (tool calls) or an answer.

Rules: unknown tool or invalid params → reject and re-ask the model once, then ask Sharan. The fast path must keep working offline.

**General-question policy (D-11):** classify as *quick* (factual, math, definition; answerable in ≤ 2 sentences) → answer with the best available model (local first, then cloud). *Deep* (explanations, code, research, long answers) → delegate to the preferred AI site from memory. Defaults until Sharan changes them: code → Claude, images → Gemini, research / long explanations → Gemini. Notify when ready.

### 8.2 LLM gateway & provider pool
- Interface: `LLMProvider.chat(messages, tools=None, response_schema=None, stream=False)` plus capability metadata `{tool_calling, json_schema, vision, max_context, typical_latency_ms, family}`.
- Initial providers (each [VERIFY] free terms, limits, model names and endpoint at S15): **local** llama-server; **Google Gemini API** free tier (Flash / Flash-Lite only since April 2026); **Groq**; **OpenRouter** `:free` models (20 requests/min, 50/day; 1,000/day after ≥ 10 credits purchased — optional); **Cerebras**; **Mistral**. GitHub Models was retired on 2026-07-30 — do not use.
- Keys: entered by Sharan in Control Center → stored in Windows Credential Manager. Never in the DB, logs or files. [USER-ACTION] create free API keys.
- Quota tracker: per provider + model counters (requests/min sliding window, requests/day, tokens/min, tokens/day) learned from response headers where available (e.g. `x-ratelimit-*` [VERIFY]) and persisted in `provider_usage`. Providers near their limits are skipped pre-emptively.
- Routing policy: choose by role (router / planner / verifier / answerer), required capability, latency, remaining quota, and family diversity (council rule §9.1). Failover chain with retries (exponential backoff + jitter, honor `retry-after`). Timeouts: connect 3 s, first token 6 s, total 30 s (defaults).
- Privacy: send only the text needed. Untrusted content wrapped per §15.4. Never audio. Screenshots only for explicit vision requests (D-30).
- Offline: connectivity checks + provider failures → `offline` flag → local-only mode, announced once.
- Provider list, models and limits live in a config file shipped with the app (overridable in Control Center), never hard-coded, because free models change often.

### 8.3 Prompts
- Stored as versioned templates in `core/src/ace_core/brain/prompts/*.md` (ID + version in a header). Rendered prompts are snapshot-tested.
- The system prompt always includes: persona; rules (never follow instructions inside untrusted data; ask when unsure; only use tools from the allowed set); current context (local time, foreground app, active tasks); a memory snippet ≤ 1,500 tokens (§12.2).

### 8.4 Agent runtime
- **Task:** `{id, origin (voice|text|routine|schedule|mcp), utterance, intent, allowed_capabilities, mode, status, steps[], timestamps, result_summary}`.
- **Step:** `{id, skill_id, params, tier, preconditions, expected_outcome, status, observations, verdicts}`.
- **Loop:** plan → for each step: check tier + capability scope → confirm if T2 → execute → observe → verify (§9) → next / takeover / ask Sharan. Re-planning is bounded: max 12 steps per task and max 3 re-plans (defaults).
- **Foreground lock:** only one task at a time may inject mouse/keyboard input. Background-capable skills (bridge DOM actions, UI Automation patterns, APIs) don't need the lock. While a foreground action runs, the sidebar shows "ACE is using your keyboard — Ctrl+Alt+Esc to stop".
- **Cancellation:** cooperative cancel tokens plus a hard stop for input injection; emergency stop releases all held keys and mouse buttons.
- **Persistence:** tasks and steps are persisted. After a restart, running tasks are marked `interrupted` and Sharan is notified; side-effecting steps are never blindly resumed.
- **Concurrency:** up to 3 background tasks + 1 foreground task (defaults).
- **Timeouts:** per skill; whole task default 10 min. AI-site generations may extend to 15 min while showing progress.

---

## §9 Verification council

### 9.1 Roles
| Role | What it is | Job |
|---|---|---|
| Supervisor | Deterministic code (never an LLM) | Enforces tiers, capability scope, budgets, timeouts, mode rules; convenes verifiers; runs takeovers; escalates to Sharan |
| Executor | Code (fast path) or an LLM (slow path) | Plans and performs the steps |
| Rule Checker | Deterministic code | Per-skill postconditions, e.g. `apps.open` → a visible window of the expected process within 10 s |
| Verifier-1/2/3 | LLMs | Judge the evidence packet against the intent |

**Diversity rule:** a verifier must be a different model family from the executor. Verifier-2 and Verifier-3 also differ from each other when possible. The local LLM counts as one family. Assignment is quota-aware.

### 9.2 Modes (D-09)
| Mode | Rule Checker | Plan review before execution | Verifier-1 | Verifier-2 and -3 |
|---|---|---|---|---|
| Fast | every step | no | only if the rule check is inconclusive | never (escalate to Sharan on failure) |
| **Balanced (default)** | every step | plans with ≥ 3 steps or any T2 step | every state-changing step | convened when the step is T2, Verifier-1 says FAIL/UNSURE, or Rule Checker and Verifier-1 disagree; majority vote |
| Paranoid | every step | always | every step | every step |

Switching: "Hey Ace, fast / balanced / paranoid mode". Per-task override: starting a command with "carefully …" runs that task in Paranoid.

### 9.3 Evidence packet (JSON, bounded size, secrets redacted)
Task intent; step `{skill, params, tier}`; expected outcome; pre/post observations: foreground window (title, process), window-list diff, bounded UI Automation snippet of the target, bridge DOM summary (URL, title, key element states), SMTC / Spotify playback state, file-system facts, bounded OCR excerpt; Rule Checker results; a downscaled screenshot only in Paranoid mode or when visual evidence is required — never stored.

### 9.4 Verdicts
`{verdict: PASS | FAIL | UNSURE, confidence: 0–1, reason, suggested_fix?}`. Majority vote among the convened verifiers. A tie or all-UNSURE → ask Sharan.

### 9.5 Takeover protocol
1. Majority FAIL → the Supervisor pauses the executor.
2. If the step has a safe `undo` (T0/T1), run it.
3. The strongest dissenting verifier (confidence + capability) becomes the new executor with the failure context; the old executor becomes a verifier.
4. At most **2 takeovers per task**. Then ask Sharan with a short summary and options: retry, try differently, cancel.
5. Every takeover is written to the audit log and shown in the sidebar (e.g. "Verifier took over: wrong window was focused").

### 9.6 Budgets
Verification calls count against provider quotas. When cloud quotas run out, the Supervisor may downgrade Balanced → Fast, but must tell Sharan ("Free limits reached — running in fast mode") — never silently. The local LLM may act as Verifier-1 for simple evidence (unlimited, free).

### 9.7 UI badges
Each step shows ✓ (verified, with a count like "✓×2"), ⚠ (unsure), ✗ (failed) or ↺ (taken over). Clicking opens the verdict details.

### 9.8 Fault-injection suite (built at S18)
Simulated: wrong window focused, app never launched, DOM selector missing, stale page, a fake "success" message, network error, provider timeout. Each has an expected council outcome that tests assert.

---

## §10 Skills catalog

### 10.1 Skill contract (every skill MUST implement)
```python
class Skill(Protocol):
    id: str                          # e.g. "apps.open"
    description: str                 # one line; becomes the LLM tool description
    params_model: type[BaseModel]    # Pydantic → JSON Schema for tool calling
    background_capable: bool         # True if no synthetic mouse/keyboard input is needed
    timeout_s: float
    examples: list[str]              # utterances (EN + Hinglish) for the golden set
    def tier_for(self, params) -> Tier: ...                 # T0..T3, may depend on params
    async def preconditions(self, ctx, params) -> list[str]: ...   # unmet → ask/explain
    async def execute(self, ctx, params) -> StepResult: ...
    async def verify(self, ctx, params, result) -> RuleCheckResult: ...  # deterministic postconditions
    async def undo(self, ctx, params, result) -> UndoResult | None: ...  # None = not undoable
```
Every skill ships with unit tests using fakes and golden-set entries.

### 10.2 Catalog

**Apps & windows (S08)**
| Skill | Examples | Tier | Verification / notes |
|---|---|---|---|
| `apps.open` | "open spotify", "spotify khol do" | T1 | Visible window of the expected process. Store apps launch via `shell:AppsFolder\<AUMID>`; desktop apps via shortcut / exe. |
| `apps.close` | "close chrome" | T1 (T2 if `force`) | Window / process gone. Graceful close first. |
| `apps.focus` | "switch to whatsapp" | T0 | Foreground window matches. |
| `windows.arrange` | "snap vs code left", "maximize this" | T1 | Window rectangle matches. |
| `windows.list` | "what's open?" | T0 | — |

**System (S19)**
| Skill | Examples | Tier | Verification / notes |
|---|---|---|---|
| `audio.volume` | "volume 30", "awaaz kam karo", "mute" | T1 | Read back endpoint volume (pycaw). Per-app volume [SHOULD]. |
| `media.control` | "pause", "next", "what's playing" | T0/T1 | Windows media controls (SMTC) state. |
| `display.brightness` | "brightness down a bit" | T1 | Read back (internal display via WMI [VERIFY]). |
| `net.radio` | "turn off bluetooth" | T1 | Radio state; if not permitted [VERIFY], open the matching `ms-settings:` page and say so. |
| `power.lock` | "lock my PC" | T1 | — |
| `power.state` | "restart", "shut down", "sleep" | T2 | Confirm + 10 s cancel window. |
| `screen.screenshot` | "take a screenshot" | T1 | File exists in `Pictures\ACE\Screenshots`. |
| `clipboard.get/set` | "copy that" | T0/T1 | — |
| `system.status` | "battery?", "what time is it" | T0 | — |
| `settings.open` | "open bluetooth settings" | T0 | `ms-settings:` URIs. |
| `focus.dnd` | "do not disturb on" | T1 | [VERIFY] a supported way exists; otherwise open the notifications settings page and say so. |

**Alarms, timers, reminders (S20)**
| Skill | Examples | Tier | Notes |
|---|---|---|---|
| `alarm.create/list/cancel/snooze/dismiss` | "wake me at 6:30", "kal subah saade chhe baje alarm" | T1 | Persisted; restored on start. |
| `timer.start/cancel/status` | "25 minute timer" | T1 | Countdown in sidebar. |
| `reminder.create/list/cancel` | "remind me at 9 to submit the assignment" | T1 | — |

Rules: ringing = sound loop + voice + actionable toast + sidebar card + phone push (S37); auto-stop after 5 min and record as missed. If the PC was asleep or off at the time → "You missed your 6:30 alarm" on wake. Optional wake-from-sleep via a Task Scheduler task with WakeToRun (opt-in per alarm [VERIFY]). Time parsing: `dateparser` + custom rules for Hinglish: "saade 6" = 6:30, "paune 7" = 6:45, "sava 7" = 7:15, "dedh" = 1:30, "dhai" = 2:30, "kal" = tomorrow (in future context), "parso" = day after tomorrow. LLM fallback with validation. Ambiguous AM/PM → ask.

**Spotify (S21)**
| Skill | Examples | Tier | Notes |
|---|---|---|---|
| `spotify.play` | "play lo-fi beats", "play my Gym playlist", "play liked songs" | T1 | Verify via playback state. |
| `spotify.control` | pause / resume / next / previous / seek / shuffle / repeat / volume | T0/T1 | — |
| `spotify.queue` | "queue Blinding Lights" | T1 | — |
| `spotify.like` | "like this song" | T1 | Undoable. |
| `spotify.now_playing` | "what's this song?" | T0 | — |

Auth: Authorization Code with PKCE. Redirect URI registered as `http://127.0.0.1/callback` **without** a port; the actual port is assigned dynamically at auth time (loopback IP literals allow this; `localhost` is not allowed). Minimal scopes: `user-read-playback-state`, `user-modify-playback-state`, `user-read-currently-playing`, `playlist-read-private`, `user-library-read`, `user-library-modify` [VERIFY]. Refresh token in Credential Manager. Search `limit` ≤ 10 (Feb 2026 Dev Mode change). No active device → launch the Spotify Store app → wait for its device → transfer playback. Fallback if the API fails: SMTC controls + `spotify:search:<query>` URI. [USER-ACTION] create a Spotify developer app (Development Mode; owner has Premium).

**Files & folders (S22)**
| Skill | Examples | Tier | Notes |
|---|---|---|---|
| `files.find` | "find my resume pdf", "files I downloaded today" | T0 | Windows Search index via a safe query builder (escape / whitelist; never string-concatenated); fallback: bounded directory walk. |
| `files.open` / `files.reveal` | "open the second one", "show it in explorer" | T0 | — |
| `files.move/copy/rename` | "move it to Documents" | T1 | Undoable. |
| `files.delete` | "delete these" | T2 | Recycle Bin only (send2trash) with count + size summary. Permanent delete is T3. |

Protected paths (refuse unless Sharan whitelists in Control Center): `C:\Windows`, `Program Files*`, `ProgramData`, other apps' `AppData`, ACE's own data/models folders, drive roots.

**Screen understanding (S23)**
| Skill | Examples | Tier | Notes |
|---|---|---|---|
| `screen.read` | "read this window", "what's on my screen?" | T0 | Windows OCR (offline) + UI Automation text. |
| `screen.selection` | "explain this", "send this to Claude" | T0 | UI Automation TextPattern; fallback: save clipboard → Ctrl+C → read → restore clipboard exactly. |
| `screen.look` | "look at my screen and tell me what's wrong" | T0 | Explicit cloud vision only (downscaled screenshot to a vision-capable provider), D-30. |

**Browser (S24):** `tabs.list`, `tabs.open`, `tabs.switch`, `tabs.close`, `tabs.search`, `tabs.reload`, `page.read`, `page.find` — T0/T1.

**AI sites (S26):** `ai.ask {site, prompt, account?, new_chat}`, `ai.image.generate {site, prompt}`, `ai.image.edit {site, image_path, instruction}`, `ai.result.get` — T1 (prompts go to Sharan's own AI accounts; no human recipient).

**YouTube (S27):** `yt.play {query}`, `yt.control`, `yt.open {channel|subscriptions|history}` — T0/T1. Never interacts with ads.

**Gmail (S28):** `mail.unread_summary {account}`, `mail.search`, `mail.open`, `mail.draft_reply` (T1), `mail.send` (T2), `mail.mark_read` (T1).

**WhatsApp (S29):** `wa.unread_summary`, `wa.open_chat {contact}`, `wa.read_chat {contact, n}`, `wa.draft {contact, text}` (T1), `wa.send {contact, text}` (T2).

**Instagram (S30):** `ig.dm_unread_summary`, `ig.open_dm {user}`, `ig.read_dm`, `ig.draft_dm` (T1), `ig.send_dm` (T2), `ig.open_profile`, `ig.open_reels`.

Messaging caps enforced by the Supervisor (WhatsApp, Instagram, Gmail): exactly 1 recipient per confirmed send; at most 10 sends per hour per service; no scheduled or repeated sends.

**Developer tools (S33)**
| Skill | Examples | Tier | Notes |
|---|---|---|---|
| `dev.open_project` | "open my ACE project" | T1 | Project registry (DB) + fuzzy match → VS Code (`code <path>`) [VERIFY CLI]. |
| `dev.terminal` | "terminal in the ACE folder" | T1 | Windows Terminal at path (`wt -d`) [VERIFY]. |
| `dev.git_status` / `dev.git_pull` | "git status", "pull" | T0 / T1 | — |
| `dev.git_commit` | "commit with message fix overlay" | T1 | Shows the message and file list. |
| `dev.git_push` | "push it" | T2 | Always confirm; `--force` is T3. |
| `dev.run` / `dev.test` | "run the tests" | T2 | Commands Sharan pre-approves per project in Control Center (e.g. `pnpm test`) run without asking; this is recorded in audit. Captured output summarized. |
| `dev.explain_error` | "send this error to Claude" | T1 | Captured output / selection → `ai.ask(claude)`. |
| `dev.open_github` | "open the PRs for ACE" | T0 | Opens repo pages in Chrome. |

Command safety: a denylist of destructive patterns (recursive delete, disk format, `git reset --hard`, `git push --force`, piping downloads into a shell, …) → T3, refused. Destructive commands are for Sharan to run manually.

**Study tools (S34):** `focus.start {minutes}` (optionally runs a routine and DND), `focus.stop/status`; `notes.add/find/open` (SQLite + Markdown export to `Documents\ACE\Notes`); `todo.add/list/done`; `links.open {alias}` (course links); `study.summarize {file|url, site}` via the AI adapters (file upload).

**Routines (S32):** `routine.run {name}`, `routine.create` (by voice: "when I say study mode, do X, Y and Z", or in Control Center), `routine.list/edit/delete`. Triggers: phrase, time, app launched, ACE started. Steps are skill calls, each verified by the council. T2 steps inside routines still confirm, unless Sharan pre-approves that specific step **in Control Center** (never by voice); pre-approvals are recorded in audit. Dry-run preview on creation.

**Dictation (S35):** `dictate.start/stop`. Inline commands: "new line", "new paragraph", "full stop", "comma", "question mark", "delete last word" [SHOULD], "stop dictation". Typing via SendInput Unicode by default; paste mode for long text (saves and restores the clipboard exactly). If focus changes during dictation → pause and notify.

**Notifications (S37):** `notify.send {title, body, channels}` (toast / voice / sidebar / phone).

**MCP (S38):** `mcp.call {server, tool, args}` — tier inherited from a per-tool mapping (unknown external tools default to T2).

**Game-mode voice subset (S36):** media and Spotify controls, volume, timers and alarms, "what time is it", reading notifications aloud, "exit game mode".

### 10.3 Contacts (D-38)
ACE's own contact book: `display_name`, aliases (e.g. "Mom", "Mummy"), WhatsApp number (E.164), Instagram handle, emails. Managed in Control Center. Local only, never synced. Messaging skills resolve recipients **only** through this book or an explicit on-screen choice confirmed by Sharan.

---

## §11 Browser bridge & site adapters

### 11.1 Why an extension
Since Chrome 136, `--remote-debugging-port` / `--remote-debugging-pipe` are ignored for the default user-data directory, so ACE cannot attach to Sharan's real, logged-in profile through CDP. A Manifest V3 extension runs inside that real profile, uses existing logins, and can act in background tabs without moving the mouse.

### 11.2 Components
- `manifest.json` (MV3) with a fixed `key` → stable extension ID.
- Service worker: connection manager (native messaging), tab operations, routing to adapters.
- Content scripts injected **on demand** with `chrome.scripting`, only on allowlisted origins.
- Adapters: one TypeScript module per site + a selectors JSON file per site.
- Native messaging host manifest registered by ACE at `HKCU\Software\Google\Chrome\NativeMessagingHosts\com.ace.bridge`, pointing to the ACE core executable, with `allowed_origins: ["chrome-extension://<ACE_EXTENSION_ID>/"]`. Host manifests cannot pass custom arguments; Chrome passes the calling extension's origin (`chrome-extension://…/`) as the first argument, so the core enters native-host mode when it sees that argument. In dev, the manifest points to a small `.bat` wrapper that runs the core from the uv environment [VERIFY registry path, manifest format and launch arguments].
- Permissions (minimal): `nativeMessaging`, `tabs`, `scripting`, `storage`, `downloads`; `debugger` only as an optional permission requested when the fallback is needed [VERIFY]. Host permissions only for: `gemini.google.com`, `claude.ai`, `chatgpt.com`, `www.youtube.com`, `mail.google.com`, `www.instagram.com`, `accounts.google.com` (account state only).

### 11.3 Lifecycle
MV3 service workers can be suspended. Keep a `connectNative` port open — an open native-messaging port keeps the worker alive [VERIFY current Chrome behavior]. Auto-reconnect with backoff; heartbeat every 20 s; the sidebar shows bridge health.

### 11.4 DOM action primitives (content script)
`waitFor(selector | text, timeout)`, `click`, `typeText` (rich editors such as ProseMirror / contenteditable need `InputEvent` / `insertText`-style input [VERIFY per site]), `pressKey`, `setFileInput` (via `DataTransfer`; fallback `chrome.debugger` → `DOM.setFileInputFiles` [VERIFY]), `observeUntil(predicate, timeout)` (MutationObserver), `extractText`, `extractImages`.
- Downloads: `chrome.downloads` can only save relative to Chrome's Downloads folder → save to `Downloads\ACE\<file>`, then the core moves the file to `Pictures\ACE\`.
- Trusted-input fallback: attach `chrome.debugger`, use `Input.insertText` / `Input.dispatchKeyEvent`, detach immediately. Chrome shows a "being debugged" bar while attached — use only when DOM input fails.

### 11.5 Account map & routing (D-08)
- Table `accounts(service, email, label)`, e.g. Gemini → student account, Gmail → personal account.
- Routing uses Google's `authuser` URL parameter (email or index) or the `/u/<index>/` path [VERIFY per service: Gmail, Gemini, YouTube].
- After the page loads, verify the active account on the page (e.g. Gmail's tab title contains the address; avatar `aria-label` on Gemini / YouTube) [VERIFY selectors]. On a mismatch → do nothing and ask Sharan.

### 11.6 Adapter interface
```ts
interface SiteAdapter {
  id: 'gemini' | 'claude' | 'chatgpt' | 'youtube' | 'gmail' | 'instagram';
  origins: string[];
  selectorsVersion: string;                        // from selectors/<id>.json
  ready(tabId: number): Promise<ReadyState>;       // loaded? logged in? right account? blocked?
  run(action: AdapterAction): Promise<AdapterResult>;
  selfTest(): Promise<SelfTestReport>;             // non-destructive check of key selectors
}
```
- **Error states** (must be detected and reported; never pretend success): `LOGGED_OUT`, `WRONG_ACCOUNT`, `CAPTCHA` (ask Sharan — ACE never solves CAPTCHAs), `RATE_LIMITED` (the site says a limit was reached), `SITE_CHANGED` (selectors missing → "Gemini's page changed; the adapter needs an update"), `NETWORK`, `TIMEOUT`, `CONTENT_REFUSED` (the AI declined).
- Selectors live in versioned JSON with primary + fallback selectors and ARIA/text-based fallbacks. Updating selectors doesn't require rebuilding the core.
- Human pace: human-like typing speed, small random delays, a per-site actions/minute cap, never parallel floods.
- Opt-in: every site adapter is disabled until Sharan enables it in Control Center after reading the ToS notice (D-07).
- Background-tab mode by default (D-24); "show me" focuses the tab.

### 11.7 Per-site notes (all [VERIFY] against the live site at the stage)
- **Gemini:** new chat, rich-text prompt box, send, response container, image results (download), image edit needs an upload; long generations show progress; must be on the mapped (student) account.
- **Claude:** new chat, ProseMirror prompt box, file attach, completion detection (e.g. the stop button disappears).
- **ChatGPT:** new chat, prompt box, completion detection, image results.
- **YouTube:** search via `/results?search_query=…`; pick the first non-ad video result; control via SMTC / DOM.
- **Gmail:** unread list via DOM, open thread, compose / reply; account routing + verification.
- **Instagram:** DMs at `/direct/inbox/`; very strict about automation → strictest pacing and send caps.

### 11.8 WhatsApp Desktop (not a website)
Approach order, verified at S29 [VERIFY]:
1. Deep link `whatsapp://send?phone=<E164>&text=<url-encoded>` to open a chat with prefilled text; press Enter only after Sharan confirms.
2. UI Automation of the WhatsApp window (its web-based UI exposes an accessibility tree) to read the chat list, unread badges and messages.
3. OCR fallback.
Verification: a new outgoing bubble with the exact text and a sent tick.

### 11.9 ToS & safety
Automating consumer websites and apps can violate their terms; accounts can be flagged or banned (R-1). Mitigations: per-site opt-in, act only on Sharan's explicit command, human pace, no scraping at scale, no bulk messaging, confirmation before every send, a kill switch per adapter.

---

## §12 Memory & personalization

### 12.1 Memory types
| Type | Example | Limit |
|---|---|---|
| Preferences | `route.image.generate = gemini`, `route.code.question = claude`, `music.focus_playlist = <spotify uri>`, `persona.address = Sharan|boss` | small values; only relevant ones injected |
| Aliases | "my project" → `E:\Projects\ace`; "college mail" → a Google account | unique phrases |
| Facts | "Sharan is a CS student", "prefers dark mode" | ≤ 150 facts, ≤ 200 characters each |
| Contacts | §10.3 | — |
| Routines | §10.2 | — |
| Episodes | Daily compacted summaries of what was done (for "what did I do yesterday?") | compacted over time |
| Short-term context | Last turns of the current conversation | in RAM, also logged |

### 12.2 Budgets
Per LLM call, the memory context is ≤ **1,500 tokens**: persona preferences always; top-k relevant preferences, aliases and facts by FTS5 keyword match + recency; episodes only when Sharan asks about the past. Overflow → compaction.

### 12.3 Learning policy (D-23)
- **Explicit:** "remember that …" → stored and confirmed back. "forget …" → deleted and confirmed. "what do you know about me?" → list.
- **Suggest-and-confirm:** when the same choice is made ≥ 2 times within 14 days for the same intent type (e.g. image tasks → Gemini), ACE asks **once**: "Want me to always use Gemini for images?" Yes → stored. No → don't ask again for 30 days.
- **Never stored:** passwords, OTPs, financial or health data, and other people's message contents beyond the current task. Message summaries are not kept long-term unless Sharan asks.

### 12.4 Compaction & retention (daily, when idle; D-26)
Raw messages older than 30 days are deleted after their episode summary exists. Episodes older than 180 days are merged into monthly summaries. Facts unused for 180 days are flagged for review in the UI (never auto-deleted).

### 12.5 UI
Memory page: search, edit, delete, pin; export.

### 12.6 Retrieval
SQLite FTS5 first. Embeddings (a small local embedding model + `sqlite-vec`) only if FTS proves insufficient — decided at S31 [MAY].

---

## §13 Database

### 13.1 Engine & settings
- SQLite 3 (bundled with Python), file `ace.db` (§5.8).
- PRAGMAs on every connection: `journal_mode=WAL`, `synchronous=NORMAL`, `foreign_keys=ON`, `busy_timeout=5000`.
- **Single-writer pattern:** all writes go through one async queue / worker to avoid "database is locked". Reads may run concurrently.
- SQLAlchemy 2.0 (typed ORM). Sync engine in a worker thread vs `aiosqlite` async engine — decided at S02 and recorded.
- Alembic migrations ship with the app and run automatically on start, after a pre-migration backup. Every schema change = one Alembic revision, referenced in that stage's Progress Log entry.
- On start: `PRAGMA quick_check`. On failure → restore the latest backup, notify Sharan, keep the corrupt file for diagnostics.

### 13.2 Rules
- Parameterized queries only (ORM, or `text()` with bound parameters). No f-strings, `%` formatting or concatenation in SQL — enforced by ruff rule `S608` and review.
- Input validated by Pydantic before reaching repositories. Repositories are the only DB access layer.
- Timestamps in UTC ISO-8601. IDs: UUIDv7 or ULID strings (decided at S02).
- Secrets are never stored in the DB (Credential Manager only).

### 13.3 Schema (v1 tables created at S02; later tables added by migrations in the listed stage)

| Table | Key columns | Stage |
|---|---|---|
| `settings` | `key` PK, `value_json`, `updated_at` | S02 |
| `audit_log` | `id`, `ts`, `actor` (user/ace/verifier/system), `event_type`, `task_id`?, `step_id`?, `tier`?, `summary`, `data_json` (redacted) | S02 |
| `conversations` | `id`, `started_at`, `ended_at`, `channel` (voice/text) | S07 |
| `messages` | `id`, `conversation_id` FK, `ts`, `role` (user/ace/system), `text`, `source` (voice/text/notification), `stt_confidence`?, `meta_json` | S07 |
| `tasks` | `id`, `conversation_id`?, `origin`, `utterance`, `intent`, `mode`, `status`, `allowed_caps_json`, `created_at`, `started_at`, `finished_at`, `result_summary`, `error_code`? | S07 |
| `task_steps` | `id`, `task_id` FK, `idx`, `skill_id`, `params_json` (redacted), `tier`, `status`, `started_at`, `finished_at`, `observation_json`, `error_code`? | S07 |
| `confirmations` | `id`, `task_id`, `step_id`, `prompt_text`, `response` (yes/no/timeout), `channel`, `responded_at` | S07 |
| `app_index` | `id`, `name`, `normalized_name`, `kind` (lnk/aumid/exe), `target`, `aumid`?, `icon_path`?, `last_seen_at`, `launch_count` | S08 |
| `models` | `id`, `kind` (stt/tts/wake/vad/llm/embed), `name`, `version`, `path`, `sha256`, `size_bytes`, `license`, `installed_at`, `status` | S14 |
| `providers` | `id`, `name`, `kind`, `base_url`, `enabled`, `priority`, `family`, `capabilities_json` (no keys) | S15 |
| `provider_usage` | PK(`provider_id`, `model`, `window_start`), `requests`, `input_tokens`, `output_tokens`, `errors`, `last_reset_at` | S15 |
| `verifications` | `id`, `step_id` FK, `verifier` (rule / model id), `provider`?, `verdict`, `confidence`, `reason`, `latency_ms`, `ts` | S18 |
| `alarms` | `id`, `kind` (alarm/timer/reminder), `label`, `fire_at_utc`, `tz`, `rrule`?, `status`, `snooze_until`?, `wake_pc`, `push_phone`, `created_at` | S20 |
| `accounts` | `id`, `service`, `email`, `label`, `authuser_hint`?, `verified_at`? | S25 |
| `adapter_state` | `adapter_id` PK, `enabled`, `tos_ack_at`?, `selectors_version`, `last_selftest_at`?, `last_selftest_ok`? | S25 |
| `contacts` | `id`, `display_name`, `aliases_json`, `whatsapp_e164`?, `instagram_handle`?, `emails_json`, `notes`? | S29 |
| `preferences` | `key` PK, `value_json`, `source` (explicit/suggested/default), `confidence`, `created_at`, `updated_at`, `last_used_at`, `use_count` | S31 |
| `aliases` | `id`, `phrase` UNIQUE, `target_type`, `target_value`, `created_at` | S31 |
| `facts` | `id`, `text`, `category`, `pinned`, `created_at`, `last_used_at` | S31 |
| `episodes` | `id`, `period_start`, `period_end`, `summary`, `task_count` | S31 |
| `choice_stats` | PK(`intent_type`, `choice`), `count`, `last_at`, `suppressed_until`? | S31 |
| `routines` | `id`, `name` UNIQUE, `trigger_type`, `trigger_value`, `steps_json`, `preapproved_steps_json`, `enabled`, `created_at`, `last_run_at`? | S32 |
| `projects` | `id`, `name`, `path`, `preapproved_commands_json`, `last_opened_at`? | S33 |
| `notes` | `id`, `title`, `body_md`, `topic`, `created_at`, `updated_at` | S34 |
| `todos` | `id`, `text`, `due_at`?, `done`, `created_at` | S34 |
| `game_list` | `id`, `process_name`, `source` (user/steam/epic/xbox/gamebar), `enabled` | S36 |
| `notifications` | `id`, `ts`, `title`, `body`, `channels_json`, `priority`, `read`, `task_id`? | S37 |
| FTS5 tables | `messages_fts`, `facts_fts`, `notes_fts` (external-content + sync triggers) | S31 / S34 |

Indexes (minimum): `messages(conversation_id, ts)`, `tasks(status, created_at)`, `task_steps(task_id, idx)`, `alarms(status, fire_at_utc)`, `provider_usage(window_start)`, `app_index(normalized_name)`, `verifications(step_id)`.

### 13.4 Backups
Daily online backup (SQLite backup API) to `data\backups\` (keep 7) + one before every migration. Restore from Control Center → Diagnostics.

### 13.5 Retention (D-26)
`messages` 30 days (after the episode summary exists) · `audit_log` 90 days · `verifications` 30 days · `tasks` / `task_steps` 90 days · `notifications` 30 days · `episodes` kept (compacted). Implemented as scheduled jobs (framework at S02, rules at S31).

### 13.6 Export / import (S44)
`.acepack` = a zip of JSON exports (settings, preferences, aliases, facts, routines, contacts, projects, notes, account map — **no tokens or keys**) + a manifest with schema version. Optional passphrase encryption (AES-GCM via `cryptography`) [SHOULD]. Import validates the schema version and shows a preview before writing.

---

## §14 UI / UX

### 14.1 Windows
- **Overlay `orb`**: ~56×56 px, docked to the screen edge (right by default; left optional), draggable along the edge; transparent, always-on-top, no taskbar entry, not focusable by default.
- **Overlay `sidebar`**: ~380 px wide, full height minus margins, slides out from the orb's edge.
- **Control Center**: a normal window (min 1000×680), opened from the tray, by right-clicking the orb, or by voice ("open ACE settings").
- **Toasts**: Windows notifications with actions (Snooze / Dismiss / Show) [VERIFY Tauri notification plugin action support; fallback: WinRT toasts from the core].

### 14.2 Overlay behavior
- Never steals focus when it appears, unless summoned by hotkey or by clicking into the text box.
- Click-through everywhere except the orb and sidebar hit areas (D-40).
- Hidden in game mode and when Sharan chooses "hide for 1 hour".
- Multi-monitor: appears on the monitor with the mouse cursor (setting). DPI-aware. Respects taskbar position.
- Stays topmost; re-asserts topmost after fullscreen apps exit and on display changes.

### 14.3 Sidebar content (top → bottom)
1. Header: "ACE", state label, mode chip (Fast / Balanced / Paranoid), health dots (internet, providers, Chrome bridge, mic).
2. Live transcript + replies (compact chat).
3. Current task card: steps with ✓ / ⚠ / ✗ / ↺ badges, progress, "show me" and "stop" buttons.
4. Background jobs (e.g. "Gemini image — generating 00:42").
5. Confirmation / clarification card (big Yes / No or option buttons; voice works too).
6. Text input: Enter sends, Esc closes, ↑ recalls history.
7. Footer toggles: mic mute, DND, hide overlay.

### 14.4 JARVIS HUD design tokens (initial; refined at S42)
| Token | Value |
|---|---|
| `--bg` | `#05080D` (panels at ~92 % opacity + backdrop blur) |
| `--panel` | `#0B1320` |
| `--line` | `#1E3A4C` |
| `--primary` | `#22D3EE` (cyan) |
| `--primary-glow` | `rgba(34, 211, 238, 0.35)` |
| `--accent` | `#3B82F6` (electric blue) |
| `--success` / `--warning` / `--danger` | `#34D399` / `#FBBF24` / `#F87171` |
| `--text` / `--text-dim` | `#E6F7FF` / `#7FA7B8` |
| Headings font | Orbitron or Rajdhani, uppercase, letter-spacing 0.08em |
| Body / mono fonts | Inter 13–14 px / JetBrains Mono |
| Shapes | 1 px glowing borders, corner brackets, thin SVG rings for the orb |
| Motion | 150–250 ms ease-out for UI; orb rings rotate (6–12 s per turn) only while active; waveform ≤ 30 fps from real audio levels; everything paused when hidden or idle > 5 s; `prefers-reduced-motion` → static |

Orb visuals per state: §5.4.

### 14.5 Control Center pages
Dashboard (status, recent tasks, quotas, latency) · History (search conversations and tasks, verification details) · Memory · Routines · Skills & Permissions (enable/disable skills, tier view, pre-approvals) · Accounts & Contacts · Providers & Keys (add, test, quotas) · Voice (audition, speed, wake sensitivity) · Devices (mic / speaker select + test) · Models (downloads, VRAM) · Browser Bridge (install / status / adapter self-tests / ToS opt-ins) · Projects (dev) · Games · Notifications (ntfy setup + QR) · Appearance (overlay skin, edge, opacity) · Diagnostics (logs, health checks, backups / restore, safe mode) · About / Updates.

### 14.6 Hotkeys
As in D-29. Every hotkey is configurable. Registration failures (conflicts) are shown in Control Center with a suggested alternative. Note: on keyboard layouts with AltGr, `Ctrl+Alt+<key>` can collide with AltGr characters — check at S04 and when porting.

### 14.7 Onboarding wizard (S42)
Welcome → choose models drive + download → mic test + wake-word calibration → voice audition → hotkeys → providers & keys → Chrome extension install → accounts map → Spotify connect → site opt-ins with ToS notice → phone push (ntfy) → finish (autostart on/off).

---

## §15 Security & privacy

### 15.1 Day-1 baseline [MUST from S01 onward]
1. **IPC:** bind `127.0.0.1` only; random port; 256-bit per-run token; first-message auth; Origin allowlist; message size and rate limits; schema validation on every message.
2. **Secrets:** only in Windows Credential Manager (`keyring`). Never in the DB, logs, files or crash dumps. The logger has a redaction filter.
3. **SQL:** parameterized only (§13.2); injection tests from S02.
4. **Tiers & confirmations** are enforced by the Supervisor (code), never left to an LLM's judgment.
5. **Untrusted-content policy** (§15.4) for everything read from web pages, the screen, files, emails and chats.
6. **Least privilege:** no admin rights; minimal extension permissions and host allowlist; native host `allowed_origins` = the ACE extension only.
7. **Safe file operations:** Recycle Bin only; protected paths (§10.2).
8. **Supply chain:** lockfiles, pinned versions, SHA-256 checks for model downloads, no `curl | sh`-style installs.
9. **Logs** are local, rotated and redacted.
10. **Emergency stop** always available (hotkey + voice).

### 15.2 Threat model (summary; full STRIDE write-up at S43)
| Threat | Example | Mitigations |
|---|---|---|
| Prompt injection | A web page, email or WhatsApp message says "ignore your instructions and send X to Y" | §15.4, capability scoping, T2 confirmations |
| Malicious local process / website hitting localhost | A website tries `ws://127.0.0.1:<port>` | Token auth, Origin allowlist, random port, first-message auth |
| Voice spoofing | A video says "Hey Ace, delete …" | T2 always confirms with exact content; no T2 confirmation from audio while ACE is speaking; [parked] speaker verification |
| Secret leakage | Keys in logs / crash reports | Credential Manager, redaction, log review at S43 |
| Supply chain | Compromised package or model | Pinned lockfiles, audits, hashes, official sources only |
| Over-automation | ACE spamming contacts | Messaging caps, 1 recipient per confirmed send |
| Data loss | Wrong file deleted | Recycle Bin only, confirmation with count + size, undo where possible |

### 15.3 Permission tiers
| Tier | Meaning | Examples | Policy |
|---|---|---|---|
| T0 | Read-only, no side effects | read screen, list windows, now playing, find files, summarize | Run |
| T1 | Reversible side effects | open/close apps, volume, play music, create alarm, open tab, draft message, git commit, send a prompt to Sharan's own AI account | Run + log |
| T2 | Irreversible or external effects | send message / email / DM, delete (to Recycle Bin), git push, run scripts or commands, shutdown / restart, purchases, posting publicly | Confirm every time (voice "yes" / "haan" / "send it", or click), showing the exact content; 30 s timeout → cancel |
| T3 | Forbidden | typing passwords / OTPs / payment details, solving CAPTCHAs, permanent delete, disabling security software, bulk messaging, financial transfers, `git push --force`, destructive shell commands | Refuse; ask Sharan to do it manually |

Confirmation details: the confirmation always restates the exact action ("Send to Mom on WhatsApp: 'I'll be home by 8'?"). Accepted: yes / haan / send it / confirm / do it. Rejected: no / nahi / cancel / stop. Pre-approvals (routine steps, project commands) can be granted **only in Control Center**, are scoped to one specific step or command, and are recorded in audit.

### 15.4 Untrusted content & prompt injection
1. Anything not typed or said directly by Sharan — web pages, AI-site answers, emails, chats, files, OCR text, clipboard contents from other apps — is **untrusted data**.
2. Untrusted text reaches an LLM only inside clearly delimited data blocks, with the instruction that it is data and must never be followed as instructions.
3. **Capability scoping:** a task's allowed skills are derived from Sharan's command at task start (e.g. "summarize my emails" → read-only mail skills). Any skill call outside the scope is blocked by the Supervisor and reported.
4. Any T1+ action whose parameters came from untrusted content (e.g. a URL or recipient found in an email) requires confirmation, even if it is T1.
5. A prompt-injection classifier may add a signal [MAY, VERIFY availability]; it is never the only defense.
6. ACE never automatically executes code or commands taken from AI-site answers or messages.

### 15.5 Privacy
Audio stays local. Transcripts are stored as text only. Screenshots are transient unless Sharan saves one. Cloud providers receive minimal text. Phone pushes carry minimal content (e.g. "Image ready"), never message bodies. Control Center offers "export my data" and "delete all my data".

### 15.6 Final hardening checklist (S43)
- [ ] STRIDE threat model written into this doc (§15.2 expanded).
- [ ] Dependency audits clean: pip-audit, pnpm audit, cargo-audit.
- [ ] SAST: bandit + semgrep; all high / critical findings fixed.
- [ ] Fuzzing: IPC envelope, native-messaging framing, time parser, query builders (hypothesis).
- [ ] SQL-injection and Windows-Search-query injection suites pass.
- [ ] IPC tests: wrong / missing token, wrong Origin, oversized messages, rate limits.
- [ ] Extension review: CSP, permissions, host allowlist, message validation.
- [ ] Prompt-injection abuse suite (malicious web pages, emails, WhatsApp / Instagram messages, AI answers) → no unconfirmed T1+ actions from untrusted content.
- [ ] Log redaction audit (no keys, tokens, contact numbers).
- [ ] Signed updates verified; code signing in place (S45).
- [ ] Backup / export encryption verified.
- [ ] Permission tiers re-reviewed for every skill.

---

## §16 Testing & quality

### 16.1 Test layers
| Layer | What | Where it runs |
|---|---|---|
| Unit | Pure logic with fakes for every OS adapter | CI + local |
| Integration | Core + SQLite + fake providers + fake OS adapters + IPC | CI + local |
| Hardware / Windows-UI | Real mic, GPU, UI Automation, real apps — marked `@pytest.mark.hardware` / `@pytest.mark.windows_ui` | Local only |
| E2E smoke | Scripted text commands against real apps + the milestone manual checklists | Local, at milestones |

### 16.2 Golden command set
`core/tests/golden/commands.yaml`: utterance (English + Hinglish variants) → expected skill + params, or an expected clarification. It grows every stage. CI runs it against the router: the fast path deterministically, the LLM path with recorded fixtures.

### 16.3 Audio fixtures
`core/tests/fixtures/audio/` — synthetic clips are committed. Sharan's own recordings ([USER-ACTION]) stay local and gitignored unless Sharan explicitly agrees to commit them. Used for wake / VAD / STT regression; prints WER and latency.

### 16.4 Council fault injection
§9.8, built at S18.

### 16.5 Adapter tests
Static fixture pages (saved HTML snapshots with personal data removed) test selectors offline. A live, non-destructive self-test command per adapter runs against the real site.

### 16.6 Performance benchmarks
`tools/bench/` scripts measure NFR-1 / NFR-2 (built at S40, run before each release).

### 16.7 CI (GitHub Actions, `windows-latest`)
Lint, type-check, unit + integration tests, golden set, UI build, `cargo check` / clippy / test, generated-TS freshness check, license check. Release workflow added at S44.

### 16.8 Milestone manual checklists
Listed per milestone in §18.1 (the SC scenarios).

---

## §17 Repository layout & conventions

### 17.1 Layout
```
E:\A.C.E\                            (git repository root)
├─ ACE_MASTER_PLAN.md                 this document
├─ CLAUDE.md                          short pointer for AI agents (created at S00)
├─ README.md, LICENSE (Apache-2.0)     README stub at S00, full README at S45
├─ .gitignore, .editorconfig, .pre-commit-config.yaml
├─ apps/
│  ├─ desktop/                         Tauri 2 app (standard create-tauri-app layout)
│  │  ├─ src/                          React UI
│  │  │  ├─ ipc/                       client + generated.ts
│  │  │  ├─ hud/                       design system components
│  │  │  ├─ overlay/  control-center/  state/
│  │  ├─ src-tauri/                    Rust shell: tray, hotkeys, windows, supervisor, click-through
│  │  └─ package.json
│  └─ bridge-extension/                Chrome MV3 extension (TypeScript)
│     └─ src/  service-worker/  content/  adapters/<site>/  selectors/<site>.json
├─ core/                               Python 3.12 package (uv project)
│  ├─ pyproject.toml, uv.lock
│  ├─ src/ace_core/
│  │  ├─ app/        main, lifecycle, config, paths, logging, events, container
│  │  ├─ ipc/        server, auth, schemas, methods
│  │  ├─ db/         engine, models, repositories, migrations/
│  │  ├─ voice/      audio, vad, wake, stt, tts, dictation, earcons
│  │  ├─ brain/      router, grammar, gateway, providers/, prompts/, agent, council, memory
│  │  ├─ skills/     base, registry, apps, windows, system, media, spotify, alarms, files, screen,
│  │  │              browser, ai_sites, youtube, gmail, whatsapp, instagram, dev, study, routines, notify, mcp
│  │  ├─ bridge/     native_host, client
│  │  ├─ models/     manager, downloader, lock
│  │  ├─ os/         Windows adapters (uia, input, windows, shell, audio, winrt, scheduler) + fakes/
│  │  ├─ context/    game_mode, connectivity, focus
│  │  └─ security/   tiers, scope, untrusted, redaction, secrets
│  └─ tests/         unit/, integration/, golden/, fixtures/
├─ tools/            gen-ts-types, bench/, wakeword-training/, dev scripts
└─ .github/workflows/  ci.yml, release.yml
```

### 17.2 Code conventions
- **Python:** ruff (format + lint), mypy strict for `ace_core` (OS adapters may use typed shims), async-first, no global mutable state except the app container, typed error codes `E_<AREA>_<NAME>`.
- **TypeScript:** strict mode, eslint + prettier, function components, one Zustand store per domain, no `any` without a comment.
- **Rust:** rustfmt + clippy (`-D warnings`); keep the shell thin — Tauri commands only, no business logic.
- **Naming:** snake_case (Python), camelCase (TS), kebab-case file names in the UI.
- **Errors** shared across IPC with stable codes; user-facing messages go through the persona layer.

### 17.3 Git
- Branches: `main` (protected once on GitHub) + `stage/sNN-short-name` per stage.
- Commits: `[SNN] imperative summary`.
- Tags: `v0.<milestone>.<n>` until `v1.0.0` at M6.

### 17.4 Disk & cache locations (dev machine; set as user environment variables at S00)
| Variable / item | Location |
|---|---|
| `RUSTUP_HOME` | `E:\.toolchains\rustup` (set **before** installing Rust) |
| `CARGO_HOME` | `E:\.toolchains\cargo` (its `bin` is on the user PATH) |
| `UV_CACHE_DIR` | `E:\.cache\uv` |
| `UV_PYTHON_INSTALL_DIR` | `E:\.toolchains\uv-python` (uv-managed CPython 3.12) |
| `UV_TOOL_DIR` / `UV_TOOL_BIN_DIR` | `E:\.toolchains\uv-tools` / `E:\.toolchains\uv-tools\bin` (pre-commit; `bin` is on the user PATH) |
| `PIP_CACHE_DIR` | `E:\.cache\pip` |
| `PRE_COMMIT_HOME` | `E:\.cache\pre-commit` |
| `HF_HOME` | `E:\.cache\huggingface` |
| `ACE_MODELS_DIR` | `E:\ACE-Models` |
| npm cache (`npm config set cache`) | `E:\.cache\npm` |
| pnpm (installed with `npm install -g --prefix`) | `E:\.toolchains\npm-global` (on the user PATH) |
| pnpm store (`pnpm config set store-dir --global`) | `E:\.cache\pnpm-store` |
| Cargo build output | inside the repo (`apps/desktop/src-tauri/target`, gitignored) |
| VS 2022 Build Tools (MSVC v143) | `E:\.toolchains\VSBuildTools2022` (shared files: `E:\.toolchains\VSShared`) |
| Windows 11 SDK 10.0.26100 | `E:\.toolchains\WindowsKits\10` (installed standalone **before** the Build Tools so they reuse it) |
| Unavoidable on C: | the Visual Studio Installer app (~0.3 GB) and Windows system runtime files |

`tools/dev/set-dev-env.ps1` applies all user-level settings above for Sharan's own terminals (run once in a normal PowerShell window; safe to re-run).

**Claude desktop sandbox — applies to every stage.** On Windows 11 the Claude desktop app runs commands inside its MSIX container: new files under `%LOCALAPPDATA%` / `%APPDATA%` and writes to `HKCU` (except a few keys the app excludes) are redirected to the app's private store and are invisible to other programs. Therefore:
1. User-level environment variables and PATH are set by Sharan with `tools/dev/set-dev-env.ps1`, never from Claude's shells.
2. Inside Claude's shells, load the toolchain environment first: `. E:\.cache\ace-setup\env.ps1`.
3. Anything other programs must see — the Chrome native-messaging host registration (S24), autostart entries (S04), ACE's real `%LOCALAPPDATA%\ACE` data — must be created by ACE itself at runtime or by Sharan, never from Claude's shell. Test those parts by launching ACE outside Claude.
4. Keep scratch and helper files on `E:` (e.g. `E:\.cache\ace-setup\`); files under AppData\Local\Temp may not stay visible.

---

## §18 Stage roadmap

Every stage uses the same template: **Goal · Prereqs · Spec · Tasks · Acceptance criteria · Tests · Definition of Done · [VERIFY] · Pitfalls · [USER-ACTION]**. The Standard Definition of Done (§0.3) always applies in addition to the stage-specific items.

### 18.1 Phases & milestones

| Phase | Stages | Theme |
|---|---|---|
| P0 | S00 | Groundwork |
| P1 | S01–S08 | Text-command spine → **M1** |
| P2 | S09–S13 | Voice → **M2** |
| P3 | S14–S18 | Brain & verification council → **M3** |
| P4 | S19–S23 | Everyday PC skills |
| P5 | S24–S30 | Browser, AI sites & messaging → **M4** |
| P6 | S31–S35 | Personal layer (memory, routines, dev, study, dictation) |
| P7 | S36–S39 | Context & connectivity → **M5** (feature-complete) |
| P8 | S40–S45 | Harden & polish (repeatable) → **M6** (v1.0) |

| Milestone | Reached after | Meaning | Acceptance scenarios (manual checklist) |
|---|---|---|---|
| M1 | S08 | Typed commands control apps and windows; overlay and Control Center work | SC-01 |
| M2 | S13 | Hands-free voice control of the same | SC-01, SC-02 |
| M3 | S18 | Smart routing, clarification, multi-step tasks, live verification | SC-18, SC-23 + §9.8 fault-injection suite |
| M4 | S30 | PC skills + browser + AI sites + messaging | SC-03, SC-05*, SC-06, SC-07, SC-08*, SC-09, SC-10, SC-11, SC-12, SC-13, SC-19, SC-20, SC-24 (*without parts delivered later: preferences S31, phone push S37, game mode S36) |
| M5 | S39 | Feature-complete personal assistant | All SC-01 … SC-24, fully |
| M6 | S45 | v1.0 public open-source release | M5 + §15.6 checklist + S44 / S45 acceptance |

---

### S00 — Workspace & repository setup
- **Goal:** A clean, reproducible dev environment with all caches on E:, and an empty monorepo skeleton that builds.
- **Prereqs:** none.
- **Spec:** §6, §17.
- **Tasks:**
  1. [USER-ACTION] Free disk space so that **C: has ≥ 15 GB free and E: has ≥ 40 GB free** (at detection: C: 14 GB, E: 22 GB). Estimated needs: C: MS C++ Build Tools + Windows SDK ≈ 5–7 GB. E: Rust ≈ 1.5 GB, pnpm store + node_modules ≈ 1.5 GB, uv cache + core environment incl. CUDA libraries ≈ 4–6 GB (+≈ 3 GB if PyTorch is needed for Chatterbox), models ≈ 5–8 GB, Rust build output ≈ 3–5 GB, repo ≈ 1 GB, plus ≥ 10 GB headroom.
  2. Set the user environment variables from §17.4 **before** installing anything.
  3. Install and record versions: MS C++ Build Tools ("Desktop development with C++": MSVC + Windows 11 SDK) [VERIFY Tauri's current Windows prerequisites]; Rust via rustup; pnpm (store on E:); confirm Python 3.12 via uv (`uv python pin 3.12`); confirm Node (record whether v26 is LTS); git user name/email [USER-ACTION].
  4. `git init` in `E:\A.C.E`. Create `.gitignore` (Python, Node, Rust, `.env*`, logs, models, local audio fixtures), `.editorconfig`, `LICENSE` (Apache-2.0), `README.md` stub, and `CLAUDE.md` (content below).
  5. Scaffold: `core/` (uv project, package `ace_core`, src layout, ruff + mypy + pytest configured); `apps/desktop` via create-tauri-app (React + TypeScript + Vite, pnpm) [VERIFY current CLI]; `apps/bridge-extension` (Vite + TS skeleton); `tools/`.
  6. pre-commit hooks: ruff, ruff-format, mypy (core), eslint + prettier, rustfmt + clippy, and a secret scanner.
  7. `.github/workflows/ci.yml`: lint + tests for core and UI + `cargo check` on `windows-latest`. It becomes active once the repo is on GitHub ([USER-ACTION] create the repo; private until v1 is fine).
  8. This file already sits at the repo root (`E:\A.C.E\ACE_MASTER_PLAN.md`); include it unchanged in the first commit.
- **`CLAUDE.md` content (≤ 40 lines):** one-line project description; "Before any work, read ACE_MASTER_PLAN.md: STATUS, §0, §4, the current stage in §18, and the last 3 entries of §23"; key dev commands (core tests, desktop dev, extension build); rules R1–R5, R7, R8 copied verbatim from §0.2.
- **Acceptance criteria:**
  - [ ] `uv run pytest` passes in `core/` (one placeholder test).
  - [ ] `pnpm tauri dev` in `apps/desktop` opens the template window.
  - [ ] `pnpm build` in `apps/bridge-extension` produces `dist/`.
  - [ ] `pre-commit run --all-files` passes.
  - [ ] `where cargo` resolves under `E:\.toolchains\cargo\bin`; `uv cache dir` is on E:.
  - [ ] Free disk space after setup is recorded in the Progress Log.
- **Tests:** placeholder tests only.
- **Definition of Done:** Standard + a toolchain-versions table in the Progress Log.
- **[VERIFY]:** Tauri 2 Windows prerequisites; create-tauri-app command and template names; pnpm install method on Windows; latest Python 3.12 patch; Node LTS status.
- **Pitfalls:** Installing Rust before setting `RUSTUP_HOME` / `CARGO_HOME` puts it on C:. Don't use Python 3.14 for the core. Never commit `node_modules`, `target/`, models or `.env`.
- **[USER-ACTION]:** free disk space; approve Build Tools install; git identity; create the GitHub repository.

### S01 — Core service skeleton
- **Goal:** `ace-core` runs as a long-lived asyncio service with config, paths, logging, an event bus and graceful shutdown.
- **Prereqs:** S00.
- **Spec:** §5.6–§5.8, §15.1, §17.2.
- **Tasks:**
  1. Entry point `ace-core` (console script) / `python -m ace_core`, flags: `--dev`, `--portable`, `--log-level`, `--native-host` (manual testing only; when Chrome launches the host, native-host mode is detected from the `chrome-extension://` origin argument, §11.2).
  2. Config with pydantic-settings: defaults → config file → env (later also the `settings` table).
  3. Path resolver: normal mode (`%LOCALAPPDATA%\ACE`) vs portable mode (an `ace-portable.flag` file next to the executable).
  4. Structured JSON logging (structlog) with daily rotation (14 days) and a **redaction filter** (API keys, tokens, bearer strings, emails, phone numbers).
  5. Typed in-process event bus (async publish / subscribe, error isolation per subscriber).
  6. Lifecycle: startup / shutdown hooks, Windows-safe signal handling, shutdown timeout (≤ 5 s), `ACE_READY port=<n>` line printed when ready (port is a stub until S03).
  7. Explicit dependency container; health model (`ok | degraded | down` per subsystem).
- **Acceptance criteria:**
  - [ ] `uv run ace-core --dev` prints the READY line and writes JSON logs under `%LOCALAPPDATA%\ACE\logs\`.
  - [ ] Ctrl+C exits cleanly in < 2 s with a shutdown log line.
  - [ ] Logging a fake API key shows it masked.
- **Tests:** config precedence; normal vs portable paths; event-bus ordering and error isolation; redaction filter; graceful shutdown.
- **Definition of Done:** Standard.
- **[VERIFY]:** pydantic-settings v2 API; asyncio signal handling with the Windows Proactor loop; structlog configuration for JSON + rotation.
- **Pitfalls:** never block the event loop; no `print` except the READY line; avoid global singletons.

### S02 — Database foundation
- **Goal:** Safe, migrated SQLite storage with repositories, backups and the retention framework.
- **Prereqs:** S01.
- **Spec:** §13, §15.1.
- **Tasks:**
  1. Engine with the §13.1 PRAGMAs; decide sync-in-worker vs `aiosqlite` and record it in §4 as a new Engineering decision.
  2. SQLAlchemy 2 models + Alembic for `settings` and `audit_log`; auto-upgrade on start with a pre-migration backup.
  3. Repository layer (the only DB access path); single-writer queue.
  4. Backup service (daily + on demand, keep 7) and restore function.
  5. Retention job framework (scheduled cleanup hooks; actual rules added by later stages).
  6. ID strategy (UUIDv7 or ULID) decided and recorded.
  7. `PRAGMA quick_check` on start with the restore path.
- **Acceptance criteria:**
  - [ ] Fresh start creates `ace.db` at the expected path in WAL mode.
  - [ ] Alembic upgrade → downgrade → upgrade works on a test DB.
  - [ ] A backup file is created and can be restored.
  - [ ] Injection payloads (e.g. `'; DROP TABLE settings;--`) stored as setting keys / values are saved literally and all tables stay intact.
- **Tests:** repository CRUD; migration round-trip; concurrent writes serialized; backup / restore; an SQL-injection payload corpus; simulated corruption → restore path.
- **Definition of Done:** Standard.
- **[VERIFY]:** SQLAlchemy 2 + SQLite WAL settings; Alembic programmatic upgrade API; SQLite backup API from Python.
- **Pitfalls:** "database is locked" → single writer + `busy_timeout`; don't share connections across threads incorrectly.

### S03 — IPC API
- **Goal:** Authenticated local API (REST + WebSocket) with typed schemas shared with the UI.
- **Prereqs:** S01, S02.
- **Spec:** §5.5, §15.1.
- **Tasks:**
  1. FastAPI app served by Uvicorn (programmatic) on `127.0.0.1:0`; the real port is printed in the READY line.
  2. Write `runtime\ipc.json` (port + token) with an ACL for the current user only [VERIFY method]; delete it on exit.
  3. WebSocket `/ws`: first-message auth within 2 s, Origin allowlist, envelope validation, 1 MiB limit, per-connection rate limit.
  4. Methods: `system.health`, `system.state.get`, `settings.get`, `settings.set`, `log.tail` (dev only). Event fan-out from the event bus to subscribed clients.
  5. Pydantic → JSON Schema → `apps/desktop/src/ipc/generated.ts` generator in `tools/`; CI freshness check.
  6. `ace-cli` dev client: `health`, `send <text>`, `watch` (events).
- **Acceptance criteria:**
  - [ ] Unauthenticated or late-auth WebSocket connections are closed.
  - [ ] A wrong Origin is rejected.
  - [ ] An authenticated client receives `state.changed` events.
  - [ ] Generated TypeScript types compile.
  - [ ] `ace-cli health` returns subsystem health.
- **Tests:** auth (missing / wrong / late token), Origin checks, oversized message, malformed JSON, unknown method, rate limit, schema round-trip, hypothesis fuzzing of the envelope parser.
- **Definition of Done:** Standard.
- **[VERIFY]:** Tauri webview Origin on Windows; FastAPI WebSocket API; Pydantic → TypeScript generation tool choice; Windows file-ACL API from Python.
- **Pitfalls:** never put the token in a URL; bind `127.0.0.1` explicitly (not `0.0.0.0`, not `localhost`).

### S04 — Tauri desktop shell
- **Goal:** The desktop app owns the tray, hotkeys and windows, and supervises the core.
- **Prereqs:** S03.
- **Spec:** §5.6, §14.1, §14.6, D-29.
- **Tasks:**
  1. Single-instance plugin (second launch focuses the first).
  2. Tray icon tinted by state; menu: Show/Hide overlay, Control Center, Mute mic, Mode ▸, Quit.
  3. Spawn the core (dev: `uv run ace-core`; prod: bundled executable) with the token env var; parse the READY line; expose `get_ipc_info` as a Tauri command.
  4. Supervisor: restart with backoff (§5.6), banner event to the UI, safe mode after 5 crashes in 5 min; kill-on-exit for the child process [VERIFY Job Object approach].
  5. Global hotkeys (D-29) with conflict detection → Control Center notice.
  6. Autostart plugin wired to a setting (default **off** until M2; S13 asks Sharan).
  7. Graceful quit (core first).
- **Acceptance criteria:**
  - [ ] Launching twice focuses the first instance.
  - [ ] Killing the core → restart within 3 s and a visible banner.
  - [ ] Each hotkey fires an event visible in the core log.
  - [ ] Quitting leaves no orphan processes (check Task Manager).
- **Tests:** Rust unit tests for the backoff / supervisor logic; manual checklist for tray and hotkeys.
- **Definition of Done:** Standard.
- **[VERIFY]:** Tauri 2 single-instance / global-shortcut / autostart plugin APIs and capability permissions; sidecar vs plain process spawning for dev and prod.
- **Pitfalls:** Tauri v1 examples are wrong for v2 — use v2 docs only; missing capability permissions silently block plugin calls.

### S05 — UI foundation, HUD design system, Control Center shell
- **Goal:** The React app structure, IPC client, state stores, the JARVIS HUD component library, and the Control Center window with every page stubbed.
- **Prereqs:** S04.
- **Spec:** §14, D-14.
- **Tasks:**
  1. TypeScript strict; Tailwind configured with the §14.4 tokens; fonts bundled locally.
  2. IPC client: connect, auth, reconnect with backoff, request / response correlation, typed events (generated types).
  3. Zustand stores: connection, conversation state, tasks, notifications, settings.
  4. HUD components: Panel, Button, Toggle, Chip, Orb (SVG rings + state animations), Waveform (canvas, level-driven), StepList with badges, ConfirmCard, ClarifyCard, Toast, TextInput.
  5. Animation pausing when hidden or idle; `prefers-reduced-motion`.
  6. Control Center window with navigation and all §14.5 pages as stubs; Dashboard shows live health and state.
  7. Dev-only component gallery page.
- **Acceptance criteria:**
  - [ ] Control Center opens from the tray and shows live core state and connection status.
  - [ ] The gallery shows every HUD component in every state.
  - [ ] With nothing animating, the webview's CPU usage is ~0 % (Task Manager).
- **Tests:** vitest component tests (states), IPC client reconnect tests (mock WebSocket), store tests.
- **Definition of Done:** Standard.
- **[VERIFY]:** Tailwind + Vite setup for the pinned versions; Motion library API; font licenses.
- **Pitfalls:** no WebGL / three.js (D-14); no continuous `requestAnimationFrame` loops when idle.

### S06 — Overlay v1 (edge orb + sidebar)
- **Goal:** An always-on-top, non-intrusive overlay with orb + slide-out sidebar and a text input.
- **Prereqs:** S05.
- **Spec:** §14.1–§14.3, D-13, D-40.
- **Tasks:**
  1. Create the `orb` and `sidebar` windows: transparent, no decorations, always-on-top, skip taskbar, not focusable by default.
  2. Click-through: a Rust thread polls the cursor (~60 Hz) and toggles ignore-cursor-events using the hit-rectangles reported by the UI.
  3. Edge docking (right default, left optional), drag along the edge, multi-monitor and DPI handling, taskbar awareness.
  4. Slide animation; the summon hotkey shows the sidebar and focuses the input; Esc closes.
  5. Sidebar sections per §14.3 (placeholder data where backends don't exist yet); "hide for 1 hour".
  6. Topmost re-assertion on display changes and after fullscreen apps exit; orb visuals driven by conversation state.
- **Acceptance criteria:**
  - [ ] The overlay stays above normal windows and borderless-fullscreen apps (Chrome F11, VS Code).
  - [ ] Clicks pass through everywhere outside the orb and sidebar.
  - [ ] Typing in another app is never interrupted when the overlay updates or animates.
  - [ ] Summon hotkey → sidebar visible with input focused in ≤ 150 ms.
  - [ ] Works on a second monitor and at 125 % / 150 % scaling.
- **Tests:** Rust unit test for hit-test logic; UI tests for sidebar sections; a documented manual checklist.
- **Definition of Done:** Standard.
- **[VERIFY]:** Tauri 2 `set_ignore_cursor_events`, focus / focusable window options, transparency with WebView2 on Windows 11, always-on-top over fullscreen windows.
- **Pitfalls:** exclusive-fullscreen games will cover the overlay (fine — game mode hides it anyway); focus stealing breaks typing; transparent windows render black if the WebView background isn't transparent.

### S07 — Command pipeline, skill framework, confirmations
- **Goal:** Typed commands flow end-to-end: router (fast path) → skill registry → Supervisor (tiers, confirmations) → task records → replies.
- **Prereqs:** S06.
- **Spec:** §5.3, §8.1 (stages 1–2), §8.4 (basic), §10.1, §15.3.
- **Tasks:**
  1. `command.submit`; normalization; fast-path grammar for: open / close / switch app (stubs until S08), "stop", "help", mode switches (stored only).
  2. Skill protocol + registry + JSON Schema export.
  3. Supervisor: tier evaluation, basic capability scope, confirmation flow (`confirm.requested` → ConfirmCard → `confirm.respond`, 30 s timeout), T3 refusal.
  4. Migrations for `conversations`, `messages`, `tasks`, `task_steps`, `confirmations`.
  5. Response composer (spoken line + detail); audit entries.
  6. Test skills: `system.echo` (T0), `demo.dangerous` (T2), `demo.forbidden` (T3).
  7. Create `core/tests/golden/commands.yaml`.
- **Acceptance criteria:**
  - [ ] "echo hello" returns a reply in the sidebar with a ✓ task.
  - [ ] "demo dangerous" shows a confirmation; "no" cancels and is logged; "yes" runs.
  - [ ] "demo forbidden" is refused with an explanation.
  - [ ] Tasks appear in Control Center → History.
- **Tests:** router golden set; Supervisor tier / confirm / timeout tests; persistence tests; IPC integration test (submit → expected event sequence).
- **Definition of Done:** Standard.
- **[VERIFY]:** none external.
- **Pitfalls:** keep LLMs out of this stage (fast path only); design the APIs so voice, routines and MCP reuse them unchanged.

### S08 — Apps & windows skills → M1
- **Goal:** Reliable app and window control, including Microsoft Store apps, with deterministic verification.
- **Prereqs:** S07.
- **Spec:** §10.2 (Apps & windows).
- **Tasks:**
  1. App index: Start Menu shortcuts (`ProgramData` + `AppData`) and Store apps via the AppsFolder → AUMIDs; refresh on start and daily; `app_index` migration.
  2. Fuzzy resolution with aliases and launch counts; clarification when the top-2 matches are close.
  3. Launch (shortcut / exe / `shell:AppsFolder\<AUMID>`); window enumeration (title, process, pid, visible, rect, monitor).
  4. Focus (respecting Windows foreground rules [VERIFY]), graceful close (force = T2), minimize / maximize / restore / snap.
  5. Rule checks for every skill; choose the UI Automation library (`uiautomation` vs pywinauto) and record it in §4.
  6. App index view in Control Center → Skills.
- **Acceptance criteria (M1):**
  - [ ] SC-01: "open spotify" (Store app) opens in ≤ 1.5 s, verified ✓.
  - [ ] "open vs code", "switch to chrome", "close notepad", "snap vs code left" all work and are verified.
  - [ ] "open spot" resolves to Spotify; an ambiguous name triggers a clarification.
  - [ ] Elevated (admin) windows are detected and reported instead of failing silently.
- **Tests:** unit tests with a fake OS adapter (index parsing, fuzzy matching, clarification thresholds); `windows_ui`-marked tests on the dev machine.
- **Definition of Done:** Standard + the M1 manual checklist passed with Sharan.
- **[VERIFY]:** AppsFolder enumeration from Python; Spotify Store AUMID; SetForegroundWindow restrictions; chosen UIA library API.
- **Pitfalls:** Store apps have no launchable exe path; Chrome has many windows per process; a non-elevated ACE cannot control elevated windows (UIPI).

### S09 — Audio I/O
- **Goal:** Robust microphone capture and speaker playback with device management and a level meter.
- **Prereqs:** S07, S05.
- **Spec:** §7.1.
- **Tasks:** device enumeration (WASAPI), selection saved, default-device following, hot-plug handling; 16 kHz mono capture into a ring buffer with 2 s pre-roll; playback queue with ≤ 100 ms interrupt; throttled `audio.level` events (15–30 Hz); earcon player; hard mic mute (stream closed) from tray / hotkey; Devices page (select, record 5 s, play back).
- **Acceptance criteria:**
  - [ ] Record 5 s and play it back from the Devices page.
  - [ ] Connecting a Bluetooth headset mid-session works without restart.
  - [ ] Mute closes the mic stream (Windows mic indicator disappears).
  - [ ] Capture alone uses < 1 % CPU.
- **Tests:** ring buffer, resampler, device-selection logic with a fake backend; `hardware`-marked tests.
- **Definition of Done:** Standard.
- **[VERIFY]:** sounddevice WASAPI options; sample rates supported by the Realtek mic array.
- **Pitfalls:** never block or run inference in the audio callback.

### S10 — VAD + STT (Hinglish benchmark)
- **Goal:** Accurate, fast English + Hinglish transcription through push-to-talk.
- **Prereqs:** S09.
- **Spec:** §7.3, §7.4, D-01, D-37.
- **Tasks:**
  1. Silero VAD segmenter.
  2. `Transcriber` interface; faster-whisper `large-v3-turbo` on CUDA with CPU fallback; vocabulary hint prompt; hallucination guards; confidence → "did you say …?".
  3. Push-to-talk hotkey → transcript → command pipeline; transcripts shown live in the sidebar.
  4. Benchmark harness: [USER-ACTION] Sharan records ~60 utterances (30 English, 30 Hinglish, typical ACE commands) with reference texts → WER + latency for each candidate (turbo, Hinglish fine-tunes with permissive licenses [VERIFY], a small CPU model) → pick defaults → update D-01 / D-37 with numbers.
- **Acceptance criteria:**
  - [ ] Push-to-talk "open spotify" executes.
  - [ ] Benchmark report committed (Sharan's audio stays local / gitignored unless Sharan agrees).
  - [ ] WER and latency meet NFR-1 / NFR-4, or the deviations are documented with a plan and approved.
- **Tests:** VAD segmentation on fixtures; transcriber interface tests with mocks / a tiny model; hallucination-guard tests.
- **Definition of Done:** Standard + benchmark table in the Progress Log.
- **[VERIFY]:** faster-whisper API and parameters; CUDA 12 cuBLAS / cuDNN packages for CTranslate2 on Windows; model download size.
- **Pitfalls:** "cuDNN DLL not found" (DLL search paths); first download goes to C: unless `HF_HOME` is set to E:.

### S11 — TTS, voice audition, persona
- **Goal:** A natural British male voice — streaming, interruptible — and persona-consistent replies.
- **Prereqs:** S09.
- **Spec:** §7.5, §7.6, D-03, D-04, D-36.
- **Tasks:**
  1. `Synthesizer` interface; Kokoro (`kokoro-onnx`, CPU) with sentence streaming.
  2. Optional Chatterbox-Turbo engine behind a flag (installs PyTorch only if Sharan picks it).
  3. Voice audition page: the same 3 sentences in every candidate (Kokoro `bm_george`, `bm_lewis`, `bm_daniel`, `bm_fable`; Chatterbox with 2–3 CC-BY British male references) → Sharan picks → saved.
  4. Speed setting; pronunciation lexicon; final earcons.
  5. Persona module: reply templates + LLM style guide (§7.6); address "Sharan" / "boss".
  6. Interrupt on "stop" / hotkey.
- **Acceptance criteria:**
  - [ ] [USER-ACTION] Sharan picks the voice; the choice is recorded in §4 (D-03 update).
  - [ ] First audio ≤ 500 ms after reply text; interruption ≤ 100 ms.
  - [ ] 10 sample replies reviewed by Sharan match the persona.
- **Tests:** sentence-chunker tests; interruption tests; engine interface mocks.
- **Definition of Done:** Standard + voice attribution (if a CC-BY reference is used) recorded for THIRD_PARTY_NOTICES.
- **[VERIFY]:** Kokoro voice IDs and license; `kokoro-onnx` package; Chatterbox-Turbo license, size and VRAM; VCTK license and attribution text.
- **Pitfalls:** PyTorch CUDA adds ~3 GB — only if Chatterbox is chosen; never clone a celebrity's voice.

### S12 — "Hey Ace" wake word
- **Goal:** A reliable custom wake word with very few false triggers.
- **Prereqs:** S10, S11.
- **Spec:** §7.2, D-02.
- **Tasks:**
  1. Reproducible training pipeline in `tools/wakeword-training/` (synthetic positives from several free TTS voices incl. Indian-English accents; augmentation; negatives) → `hey_ace.onnx`.
  2. [USER-ACTION] Sharan records ≥ 50 "hey ace" samples (different distances, tones) and ~10 min of normal room / media audio.
  3. Integrate the detector (CPU) with thresholds and two-stage acceptance; sensitivity slider; false-wake score log; disabled during TTS.
  4. Wake → LISTENING with pre-roll.
- **Acceptance criteria:**
  - [ ] ≥ 95 % detection on Sharan's held-out samples.
  - [ ] False wakes measured on ≥ 2 h of YouTube / music / typing and extrapolated to ≤ 1 per 8 h.
  - [ ] The wake loop uses ≤ 2 % CPU.
- **Tests:** offline evaluation script with fixtures; threshold unit tests.
- **Definition of Done:** Standard + evaluation numbers in the Progress Log.
- **[VERIFY]:** openWakeWord training process and the licenses of the voices / data used; alternative engines if quality is insufficient.
- **Pitfalls:** training on one voice generalizes badly; cover Indian-English accents; never ship NC pre-trained models.

### S13 — Voice loop & state machine → M2
- **Goal:** The full hands-free loop, wired to the overlay states.
- **Prereqs:** S10, S11, S12.
- **Spec:** §5.4, §7.7, FR-IN-5.
- **Tasks:**
  1. Conversation state machine (§5.4) in the core, emitting `state.changed`.
  2. wake → listen → transcribe → pipeline → speak → follow-up (8 s) → asleep; half-duplex gating.
  3. Voice confirmations (yes / haan / no / nahi …) and voice clarifications.
  4. Per-stage latency instrumentation (logs + Dashboard).
  5. Ask Sharan whether autostart should now default to on.
- **Acceptance criteria (M2):**
  - [ ] SC-02 works hands-free.
  - [ ] "Hey Ace, stop" (after TTS ends) and the hotkey (any time) interrupt.
  - [ ] Voice confirmation works on `demo.dangerous`.
  - [ ] Simple command: end of speech → visible action ≤ 1.5 s (timings reported).
- **Tests:** state-machine unit tests covering every transition; integration with fake audio / STT / TTS.
- **Definition of Done:** Standard + M2 manual checklist passed with Sharan.
- **[VERIFY]:** none external.
- **Pitfalls:** races between TTS end and the follow-up window; ACE hearing itself (half-duplex must gate the mic path).

### S14 — Model manager & local LLM
- **Goal:** Managed local models (download, verify, load / unload) and a local LLM server.
- **Prereqs:** S13.
- **Spec:** §7.8, D-32.
- **Tasks:**
  1. `models.lock.json` (URL, SHA-256, size, license); downloader with resume, verification, progress events and a free-space check; `models` migration.
  2. Models-dir selection (default `E:\ACE-Models`).
  3. VRAM accounting via NVML; budget enforcement with priorities.
  4. llama-server lifecycle: download the official CUDA Windows build [VERIFY asset names], start with the chosen model, health check, stop.
  5. Choose the local LLM: best ≤ 4 GB-VRAM (Q4) instruct model with reliable tool calling and a permissive license [VERIFY candidates]; CPU fallback; idle unload.
  6. Models page in Control Center.
- **Acceptance criteria:**
  - [ ] Fresh setup downloads models to `E:\ACE-Models` with verified hashes.
  - [ ] llama-server answers a tool-calling test request.
  - [ ] With STT + LLM loaded, VRAM ≤ 5 GB; unloading frees it.
- **Tests:** downloader (hash mismatch, resume, low disk); budget logic; server supervisor with a fake process.
- **Definition of Done:** Standard + model licenses recorded.
- **[VERIFY]:** llama.cpp Windows CUDA release assets and server flags; NVML Python binding; model licenses.
- **Pitfalls:** CUDA runtime DLL mismatches; antivirus scanning large files; never download into C:.

### S15 — LLM gateway & provider pool
- **Goal:** Reliable access to free cloud models with failover and quota awareness.
- **Prereqs:** S14.
- **Spec:** §8.2.
- **Tasks:**
  1. Provider interface and implementations: local, Gemini, Groq, OpenRouter, Cerebras, Mistral — each [VERIFY] at implementation time.
  2. Providers & Keys page: add key → Credential Manager → "test key" button. [USER-ACTION] create free keys.
  3. Quota tracker (headers + local counters) with `providers` / `provider_usage` migrations.
  4. Routing by role / capability / family; retries with backoff; timeouts; streaming.
  5. Normalize tool calling and JSON-schema output across providers.
  6. Offline detection; provider config file (models, limits) overridable in Control Center; mock provider for tests.
- **Acceptance criteria:**
  - [ ] With ≥ 2 cloud keys + local, a planner request succeeds.
  - [ ] A simulated 429 on provider A fails over to B transparently.
  - [ ] Quotas are visible on the Dashboard.
  - [ ] No key appears in logs, DB or crash output (grep test).
- **Tests:** failover; quota windows; tool-call normalization; redaction.
- **Definition of Done:** Standard + the verified provider table (free limits, date checked) in the Progress Log.
- **[VERIFY]:** each provider's current free tier, model names, OpenAI compatibility and rate-limit headers.
- **Pitfalls:** free model lists change weekly — keep them in config, not code.

### S16 — Smart router, clarification, general questions
- **Goal:** Natural-language understanding beyond the grammar, with asking-back and the D-11 policy.
- **Prereqs:** S15.
- **Spec:** §8.1, §8.3, D-11, FR-BR-3, FR-SEC-3.
- **Tasks:**
  1. Router stages 3–4 using tool schemas from the registry.
  2. Versioned prompt templates with snapshot tests; context assembly (time, foreground app, active tasks; memory placeholder until S31).
  3. Clarification generation (options); STT-confidence "did you say …?".
  4. Quick vs deep classifier. Quick → answer (local first, then cloud). Deep → route to the delegation interface; until S26 it replies "I'll be able to send that to <site> once the browser bridge is ready" (no fake answers).
  5. Untrusted-data wrapping helpers (§15.4) used by every prompt that includes external text.
  6. Golden set +50 utterances including Hinglish ("spotify khol do", "volume thoda kam karo", "kal subah 6 baje alarm laga do").
- **Acceptance criteria:**
  - [ ] ≥ 95 % of golden utterances route correctly (LLM path with recorded fixtures).
  - [ ] SC-18: ambiguous commands trigger a clarification.
  - [ ] "what's 18 percent of 2450" is answered in ≤ 2 s.
  - [ ] With the network off, fast-path commands still work and ACE says cloud features are unavailable.
- **Tests:** golden set; prompt snapshots; schema-validation rejection tests (unknown tools / bad params).
- **Definition of Done:** Standard.
- **[VERIFY]:** tool-calling formats of the chosen local and cloud models.
- **Pitfalls:** LLMs invent tools or parameters → strict validation; never execute unvalidated parameters.

### S17 — Agent runtime
- **Goal:** Multi-step tasks with progress, background execution, foreground lock, cancellation and persistence.
- **Prereqs:** S16.
- **Spec:** §8.4, FR-CORE-4, FR-SEC-2.
- **Tasks:** Task / Step engine; plan-execute loop with bounded re-planning; capability-scope enforcement; foreground lock + input-injection guard (release keys on cancel); background queue (3); progress events and sidebar task cards; "show me" hook; emergency stop; interrupted-task handling after restart; per-skill and per-task timeouts.
- **Acceptance criteria:**
  - [ ] "open spotify and vs code, then snap vs code left" runs as 3 verified steps.
  - [ ] Emergency stop mid-task stops within 200 ms and releases inputs.
  - [ ] Killing the core mid-task → after restart the task is `interrupted` and Sharan is notified.
  - [ ] A skill call outside the task's capability scope is blocked and reported.
- **Tests:** engine state transitions, cancellation, scope violations, timeouts, persistence — all with fake skills.
- **Definition of Done:** Standard.
- **[VERIFY]:** none external.
- **Pitfalls:** stuck modifier keys after a cancelled injection — always release in `finally`.

### S18 — Verification council → M3
- **Goal:** Live verification with modes, voting, takeover, audit and UI badges.
- **Prereqs:** S17.
- **Spec:** §9, D-09.
- **Tasks:** evidence-packet builder (bounded, redacted); verifier prompts; family-diversity assignment; Fast / Balanced / Paranoid + voice switching + "carefully …" override; voting; takeover protocol; budget-aware downgrade with notice; `verifications` migration; UI badges and details; fault-injection suite (§9.8).
- **Acceptance criteria (M3):**
  - [ ] The fault-injection suite passes.
  - [ ] Balanced mode adds ≤ 1.5 s median per state-changing step (measured).
  - [ ] SC-23: "Hey Ace, paranoid mode" works.
  - [ ] A takeover is visible in the sidebar and the audit log.
- **Tests:** council logic with fake verifiers (every vote combination), takeover limit, budget downgrade notice, evidence redaction.
- **Definition of Done:** Standard + M3 manual checklist passed with Sharan.
- **[VERIFY]:** none external beyond S15's providers.
- **Pitfalls:** correlated errors when executor and verifier share a model family — enforce the diversity rule in code.

### S19 — System controls
- **Goal:** Everyday system controls by voice and text.
- **Prereqs:** S18.
- **Spec:** §10.2 (System).
- **Tasks:** implement every System skill with rule checks; Hinglish phrasings in the golden set; `ms-settings:` deep links; power actions with confirmation + 10 s cancel window; screenshots saved to `Pictures\ACE\Screenshots` on request.
- **Acceptance criteria:**
  - [ ] Each System skill works on the dev machine and is verified.
  - [ ] Brightness works on the internal display.
  - [ ] Wi-Fi / Bluetooth toggles either work or open the correct Settings page with an explanation.
  - [ ] SC-04 media / volume parts work in normal mode.
- **Tests:** unit tests with fakes; `hardware`-marked tests.
- **Definition of Done:** Standard.
- **[VERIFY]:** pycaw API; WMI brightness; WinRT Radios from an unpackaged Python app; programmatic Do-Not-Disturb feasibility; SMTC package API.
- **Pitfalls:** some toggles need app capabilities that unpackaged apps lack — fall back honestly.

### S20 — Alarms, timers, reminders
- **Goal:** Dependable time-based features that survive restarts and sleep.
- **Prereqs:** S18.
- **Spec:** §10.2 (Alarms), D-26.
- **Tasks:** scheduler service (wall-clock + monotonic, timezone-aware, sleep/resume detection); natural-language time parsing incl. Hinglish rules + ambiguity questions; ringing UX (sound loop, voice, actionable toast, sidebar card); snooze / dismiss by voice; recurring alarms (RRULE subset); missed-alarm notices; opt-in wake-from-sleep via Task Scheduler WakeToRun; `alarms` migration; timer countdowns in the sidebar.
- **Acceptance criteria:**
  - [ ] An alarm 2 min ahead rings on every channel; "snooze 10" works.
  - [ ] Alarms survive a core restart.
  - [ ] Sleeping through an alarm → "missed" notice on wake (or the PC wakes if opted in).
  - [ ] SC-08 (without phone push) and SC-09 pass.
- **Tests:** fake-clock scheduler tests; parser table tests (English + Hinglish: "saade 6", "paune 7", "kal subah", "parso"); persistence tests.
- **Definition of Done:** Standard.
- **[VERIFY]:** Task Scheduler WakeToRun from Python (COM / `schtasks` XML); `dateparser` behavior for the phrases above.
- **Pitfalls:** "6" without AM/PM is ambiguous — ask; laptops on battery may have wake timers disabled.

### S21 — Spotify
- **Goal:** Full Spotify control via the official Web API (Premium), with a fallback.
- **Prereqs:** S18.
- **Spec:** §10.2 (Spotify), D-06.
- **Tasks:** [USER-ACTION] Sharan creates a Spotify developer app (Development Mode), registers the redirect `http://127.0.0.1/callback` (no port) and pastes the Client ID into ACE; PKCE flow with a loopback server on a dynamic port; token refresh (Credential Manager); all Spotify skills; device activation (launch the Store app → wait for the device → transfer playback); SMTC + `spotify:search:` fallback; verification via playback state.
- **Acceptance criteria:**
  - [ ] SC-03 and the SC-04 Spotify parts pass.
  - [ ] "play my <playlist name>" and "like this song" work.
  - [ ] With Spotify closed, ACE launches it and plays.
- **Tests:** API client with recorded fixtures; PKCE unit tests; device-selection logic tests.
- **Definition of Done:** Standard.
- **[VERIFY]:** Feb-2026 Dev-Mode endpoint availability (Player endpoints; search `limit` ≤ 10), required scopes, rate limits, redirect-URI rules.
- **Pitfalls:** "no active device" errors; never use `localhost` in the redirect URI.

### S22 — Files & folders
- **Goal:** Safe file finding and handling.
- **Prereqs:** S18.
- **Spec:** §10.2 (Files), §15.1.
- **Tasks:** Windows Search query builder (escaping / whitelisting; no string concatenation) with bounded-walk fallback; open / reveal; move / copy / rename with undo; delete → Recycle Bin with count + size summary (T2); protected paths; result lists in the sidebar ("open the second one").
- **Acceptance criteria:**
  - [ ] SC-20 passes.
  - [ ] Find by name, type and date works.
  - [ ] "undo that" reverses the last move / rename.
  - [ ] Protected paths are refused with an explanation.
- **Tests:** query-builder injection tests (quotes, brackets, keywords in file names); path-guard tests; undo tests.
- **Definition of Done:** Standard.
- **[VERIFY]:** Windows Search (SystemIndex) access from Python; send2trash behavior on Windows.
- **Pitfalls:** Windows Search uses a SQL-like syntax — injection matters here too.

### S23 — Screen understanding
- **Goal:** Read and explain what's on screen, privately.
- **Prereqs:** S18.
- **Spec:** §10.2 (Screen), D-30.
- **Tasks:** capture (window / screen / region); Windows OCR via WinRT; UI Automation text; selected-text capture with exact clipboard restore; "explain this" (local text → LLM, wrapped as untrusted data); explicit "look at my screen" cloud vision; nothing stored by default.
- **Acceptance criteria:**
  - [ ] SC-24 passes.
  - [ ] "explain this" on a selected terminal error returns an explanation.
  - [ ] The clipboard is restored byte-for-byte after selection capture.
- **Tests:** OCR wrapper with fixture images; clipboard save / restore tests.
- **Definition of Done:** Standard.
- **[VERIFY]:** pywinrt OCR package and language availability; screen-capture method (mss vs Windows Graphics Capture).
- **Pitfalls:** never send screenshots to the cloud without an explicit request.

### S24 — Chrome bridge
- **Goal:** A secure, persistent connection between ACE and Sharan's real Chrome.
- **Prereqs:** S18.
- **Spec:** §11.1–§11.4, §15.1.
- **Tasks:** MV3 extension with a fixed key / ID; service-worker connection manager; native-host mode (§11.2); HKCU host registration from ACE (install / repair button); handshake + token auth; heartbeat / reconnect; tab skills; `page.read`; DOM primitives; untrusted tagging of all page content; Browser Bridge page with install steps ([USER-ACTION] load the unpacked extension from `dist/`).
- **Acceptance criteria:**
  - [ ] "list my tabs", "switch to the YouTube tab", "open github.com in a new tab", "close this tab" all work and are verified.
  - [ ] The bridge survives a Chrome restart and service-worker suspension.
  - [ ] Page-text extraction works on the test pages.
- **Tests:** extension unit tests (vitest); native-messaging framing tests (length prefix, size limits); integration with local test pages.
- **Definition of Done:** Standard.
- **[VERIFY]:** native-messaging registry path, manifest format and message-size limits; MV3 service-worker keep-alive behavior; optional `debugger` permission.
- **Pitfalls:** the extension ID must match the host manifest's `allowed_origins`; MV3 workers get suspended.

### S25 — Site adapter framework
- **Goal:** A common, robust way to operate websites safely.
- **Prereqs:** S24.
- **Spec:** §11.5, §11.6, D-07, D-08, D-24.
- **Tasks:** adapter interface + base utilities; versioned selectors loader; ready / account / error-state detection helpers; human-pace input; background-tab mode + "show me"; downloads → move to `Pictures\ACE`; opt-in flow with the ToS notice; accounts map UI + `authuser` routing + on-page verification; per-adapter self-test; long-task progress + notifications; `accounts` / `adapter_state` migrations.
- **Acceptance criteria:**
  - [ ] A reference adapter on local test pages detects every error state (§11.6) correctly.
  - [ ] Account routing opens the mapped account and refuses on a mismatch.
  - [ ] Disabled adapters cannot run until opted in.
- **Tests:** framework unit tests with fixture pages for each error state; account-mismatch tests.
- **Definition of Done:** Standard.
- **[VERIFY]:** `authuser` behavior per Google service; download-path behavior of `chrome.downloads`.
- **Pitfalls:** never report success without positive evidence on the page.

### S26 — Gemini, Claude, ChatGPT adapters
- **Goal:** ACE can use Sharan's AI subscriptions on Sharan's command.
- **Prereqs:** S25.
- **Spec:** §11.7, FR-SK-AI-1, D-11.
- **Tasks:** per site: new chat, type prompt, submit, detect completion, extract the answer (Markdown); Gemini image generation + editing (upload); download images; notifications; connect the S16 delegation interface; default routing until S31 (images → Gemini, code → Claude, deep explanations → Gemini).
- **Acceptance criteria:**
  - [ ] SC-05 (default routing, no phone push yet), SC-06 and the deep part of SC-07 pass.
  - [ ] Each adapter's self-test passes.
  - [ ] A logged-out state is detected and reported (SC-19).
- **Tests:** selector tests on saved fixture pages; completion-detection logic tests.
- **Definition of Done:** Standard + the date the selectors were verified.
- **[VERIFY]:** live DOM structure and selectors of each site; each site's current terms.
- **Pitfalls:** rich editors ignore plain `value` assignment; streaming answers look "done" too early — wait for a positive completion signal.

### S27 — YouTube
- **Goal:** Search, play and control YouTube.
- **Prereqs:** S25.
- **Spec:** §10.2 (YouTube), §11.7.
- **Tasks:** search via the results URL; pick the first non-ad video; play; controls via SMTC / DOM; open channel / subscriptions / history.
- **Acceptance criteria:**
  - [ ] SC-13 passes.
  - [ ] Ads are never clicked or interacted with.
- **Tests:** result-picking logic on fixture pages.
- **Definition of Done:** Standard.
- **[VERIFY]:** YouTube DOM selectors.
- **Pitfalls:** sponsored results look like normal results.

### S28 — Gmail (multi-account)
- **Goal:** Read, summarize, draft and send email on the right account.
- **Prereqs:** S25.
- **Spec:** §10.2 (Gmail), §11.5.
- **Tasks:** unread summary (sender, subject, one-line gist), search, open, draft reply, send (T2), mark read; account routing + verification; summaries not stored long-term; email content treated as untrusted.
- **Acceptance criteria:**
  - [ ] SC-11 passes.
  - [ ] Wrong-account protection: a mapping mismatch → refuse and ask.
  - [ ] A send always shows the exact recipient, subject and body for confirmation.
- **Tests:** fixture-page tests; account-mismatch tests; prompt-injection test emails (no unconfirmed actions).
- **Definition of Done:** Standard.
- **[VERIFY]:** Gmail DOM selectors; `authuser` routing.
- **Pitfalls:** emails can contain instructions aimed at ACE — they are data only.

### S29 — WhatsApp Desktop
- **Goal:** Read, summarize, draft and send WhatsApp messages safely.
- **Prereqs:** S18.
- **Spec:** §10.2 (WhatsApp), §10.3, §11.8, D-38.
- **Tasks:** contact book UI + `contacts` migration; open chat via deep link; read unread via UI Automation; draft (prefill); send after confirmation; verify the outgoing bubble; messaging caps; human pace.
- **Acceptance criteria:**
  - [ ] SC-10 passes.
  - [ ] Unknown contacts are never guessed — ACE asks.
  - [ ] Caps are enforced (tested with a fake clock).
- **Tests:** contact resolution tests; caps tests; UIA reading tests on the real app (`windows_ui`).
- **Definition of Done:** Standard.
- **[VERIFY]:** WhatsApp Desktop UI Automation exposure and deep-link behavior on the installed version; WhatsApp terms.
- **Pitfalls:** WhatsApp is strict about automation — keep pacing human and never bulk-send.

### S30 — Instagram (web) → M4
- **Goal:** Read, summarize, draft and send Instagram DMs; open profiles and reels.
- **Prereqs:** S25.
- **Spec:** §10.2 (Instagram), §11.7.
- **Tasks:** DM unread summary, open DM, read, draft, send (T2), open profile / reels; strictest pacing and caps.
- **Acceptance criteria (M4):**
  - [ ] SC-12 passes.
  - [ ] The M4 checklist (§18.1) passes with Sharan.
- **Tests:** fixture-page tests; caps tests.
- **Definition of Done:** Standard + M4 manual checklist.
- **[VERIFY]:** Instagram DOM selectors; Instagram terms.
- **Pitfalls:** Instagram rate-limits and flags fast actions — keep it slow.

### S31 — Memory & preferences
- **Goal:** Compact, editable memory that makes ACE personal.
- **Prereqs:** S16, S26.
- **Spec:** §12, D-23, D-26.
- **Tasks:** `preferences`, `aliases`, `facts`, `episodes`, `choice_stats` + FTS5 migrations; retrieval with the 1,500-token budget; "remember / forget / what do you know about me" flows; suggest-and-confirm learning; daily compaction + retention jobs; Memory page (search, edit, delete, pin, export); decide on embeddings (FTS-only unless proven insufficient).
- **Acceptance criteria:**
  - [ ] SC-21 passes.
  - [ ] The memory budget is never exceeded (test with 500+ facts).
  - [ ] Memory items can be edited and deleted from the UI.
  - [ ] SC-05 now uses the learned / explicit preference.
- **Tests:** retrieval ranking, budget enforcement, learning thresholds (2 choices / 14 days, 30-day suppression), compaction / retention with a fake clock.
- **Definition of Done:** Standard.
- **[VERIFY]:** SQLite FTS5 availability in the bundled Python SQLite.
- **Pitfalls:** never store passwords, OTPs or other people's message contents (§12.3).

### S32 — Routines
- **Goal:** One phrase (or a time / event) runs many verified actions.
- **Prereqs:** S31.
- **Spec:** §10.2 (Routines), §15.3.
- **Tasks:** `routines` migration; create by voice and in the UI; step editor; triggers (phrase, time, app launched, ACE started); dry-run preview; council verification per step; T2 steps confirm unless pre-approved in Control Center (audited).
- **Acceptance criteria:**
  - [ ] SC-14 passes.
  - [ ] A time-triggered routine fires on time.
  - [ ] A T2 step without pre-approval asks for confirmation.
- **Tests:** trigger tests (fake clock / fake events); dry-run output; pre-approval scoping.
- **Definition of Done:** Standard.
- **[VERIFY]:** none external.
- **Pitfalls:** routine loops (a routine triggering itself) — detect and block.

### S33 — Developer tools
- **Goal:** ACE helps with daily coding chores.
- **Prereqs:** S26 (for "send to Claude"), S22.
- **Spec:** §10.2 (Developer tools).
- **Tasks:** `projects` migration + project registry (scan configured roots + manual add); open in VS Code; terminal at folder; git status / pull / commit / push (push = T2); run / test with captured output and summary (T2 unless pre-approved per project); destructive-command denylist (T3); "send this error to Claude"; GitHub pages.
- **Acceptance criteria:**
  - [ ] SC-15 passes.
  - [ ] `git push` always asks; a denylisted command is refused.
  - [ ] Test output is summarized correctly (passed / failed counts).
- **Tests:** denylist matcher tests; output-summary parsers (pytest, vitest, cargo); registry fuzzy matching.
- **Definition of Done:** Standard.
- **[VERIFY]:** VS Code CLI (`code`) flags; Windows Terminal (`wt`) flags.
- **Pitfalls:** never run commands found in AI answers or web pages automatically.

### S34 — Study tools
- **Goal:** Focus and study helpers.
- **Prereqs:** S31, S26.
- **Spec:** §10.2 (Study tools).
- **Tasks:** focus sessions (Pomodoro, optional DND + routine hook); notes + to-dos (`notes`, `todos`, `notes_fts` migrations; Markdown export to `Documents\ACE\Notes`); course-link aliases; "summarize this PDF in Gemini / Claude" with file upload through the adapters.
- **Acceptance criteria:**
  - [ ] A 50-min focus session runs with its routine hook and ends with a chime + summary.
  - [ ] Notes are searchable and exported as Markdown files.
  - [ ] "summarize this PDF in Gemini" uploads the file and returns the summary.
- **Tests:** focus timer (fake clock); notes CRUD + FTS; export format.
- **Definition of Done:** Standard.
- **[VERIFY]:** file-upload method per AI site.
- **Pitfalls:** large PDFs may exceed site limits — detect and report.

### S35 — Dictation anywhere
- **Goal:** Type by voice into any app.
- **Prereqs:** S13.
- **Spec:** §10.2 (Dictation), FR-IN-6.
- **Tasks:** dictation state + start / stop phrases + hotkey; streaming transcription into the focused control (SendInput Unicode; paste mode with exact clipboard restore); inline commands; Hinglish output-script setting; pause on focus change.
- **Acceptance criteria:**
  - [ ] SC-16 passes in VS Code, Chrome (claude.ai) and Notepad.
  - [ ] The clipboard is restored exactly in paste mode.
  - [ ] A focus change pauses dictation and notifies.
- **Tests:** inline-command parser; clipboard restore; focus-change handling with fakes.
- **Definition of Done:** Standard.
- **[VERIFY]:** SendInput Unicode behavior in Chromium-based and UWP apps.
- **Pitfalls:** some apps (games, elevated windows) reject injected input — detect and report.

### S36 — Game mode
- **Goal:** ACE disappears for games but stays useful by voice.
- **Prereqs:** S13, S14.
- **Spec:** D-15, §10.2 (Game-mode voice subset).
- **Tasks:** detection (`SHQueryUserNotificationState` full-screen / busy states + foreground full-screen check + game install paths (Steam, Epic, Xbox) + Game Bar's game list + a user list; `game_list` migration); hide overlay; unload GPU models (STT → CPU model); voice-only subset; auto-restore; Games page.
- **Acceptance criteria:**
  - [ ] SC-17 passes with at least one Steam game and one borderless-window game ([USER-ACTION] Sharan picks the games).
  - [ ] VRAM used by ACE ≤ 0.3 GB in game mode.
  - [ ] No false game-mode triggers when watching fullscreen YouTube (or it's handled by the user list).
- **Tests:** detection logic with fakes; transition tests (enter / exit).
- **Definition of Done:** Standard.
- **[VERIFY]:** `SHQueryUserNotificationState` values; Game Bar `GameConfigStore` registry usage.
- **Pitfalls:** fullscreen video is not a game — combine signals.

### S37 — Notifications hub + phone push (ntfy)
- **Goal:** One notification system for toasts, voice, sidebar and Sharan's phone.
- **Prereqs:** S20, S26.
- **Spec:** FR-OUT-3, FR-CTX-2, D-39.
- **Tasks:** `notifications` migration; unified model with priority + DND rules; ntfy publisher (random 32+ character topic, minimal content); Notifications page with a QR code for subscribing ([USER-ACTION] install the ntfy app); hooks for task done, alarms, reminders, failures.
- **Acceptance criteria:**
  - [ ] The phone receives a push for a finished Gemini image and for an alarm (completes SC-05 and SC-08).
  - [ ] DND suppresses non-urgent channels.
  - [ ] Push bodies contain no message contents or personal data.
- **Tests:** routing rules; content-minimization tests; publisher with a mock server.
- **Definition of Done:** Standard.
- **[VERIFY]:** ntfy publish API and public-server limits.
- **Pitfalls:** public ntfy topics are readable by anyone who knows the name — keep it long and random, content minimal.

### S38 — MCP connectivity
- **Goal:** ACE talks MCP in both directions.
- **Prereqs:** S18.
- **Spec:** FR-CTX-3, D-17.
- **Tasks:** ACE as MCP **server** (exposes selected skills; ACE's tiers, scope and confirmations still apply on ACE's side); ACE as MCP **client** (Windows on-device agent connectors if available on Sharan's build; local MCP servers configured in Control Center); unknown external tools default to T2; outputs from external tools are untrusted.
- **Acceptance criteria:**
  - [ ] Claude Code can call ACE's `apps.open` through ACE's MCP server; a T2 skill still requires confirmation in ACE.
  - [ ] ACE can call at least one MCP tool as a client (a Windows connector if available, otherwise a local test server).
- **Tests:** MCP server contract tests; tier enforcement for MCP-originated tasks.
- **Definition of Done:** Standard.
- **[VERIFY]:** MCP Python SDK version / API; Windows on-device agent registry availability and access method on build 26300.
- **Pitfalls:** MCP clients must never bypass confirmations.

### S39 — Overlay skins 2 & 3 → M5
- **Goal:** Optional top-center pill and slim-bar skins — only if they're stable (D-13).
- **Prereqs:** S06 and all of P6.
- **Spec:** FR-UI-5, D-13.
- **Tasks:** both skins as pure presentation over the same state store; runtime switching in Appearance; a 1-hour soak test with frequent switching.
- **Acceptance criteria (M5):**
  - [ ] Switching skins doesn't restart the core or lose state.
  - [ ] The soak test shows no crash and no memory growth > 10 %. **If either fails, remove the extra skins and record the decision in §4** (Sharan's rule).
  - [ ] The M5 checklist (every SC fully) passes with Sharan.
- **Tests:** UI tests per skin; soak-test script.
- **Definition of Done:** Standard + M5 manual checklist.
- **[VERIFY]:** none external.
- **Pitfalls:** duplicated logic across skins — keep skins presentational only.

### S40 — Performance pass
- **Goal:** Meet NFR-1 / NFR-2 with measurements, not guesses.
- **Prereqs:** M5.
- **Spec:** §3.2, §16.6.
- **Tasks:** `tools/bench/` scripts; profile startup, idle and command latency; optimize; re-measure; propose target changes to Sharan if needed.
- **Acceptance criteria:**
  - [ ] A benchmark table (before / after) is in the Progress Log.
  - [ ] All targets met, or deviations approved by Sharan and recorded in §3.2.
- **Tests:** benchmark scripts runnable on demand.
- **Definition of Done:** Standard.
- **[VERIFY]:** none external.
- **Pitfalls:** don't optimize without a measurement first.

### S41 — Reliability pass + barge-in
- **Goal:** ACE survives long sessions and failures; full-duplex "stop".
- **Prereqs:** S40.
- **Spec:** NFR-3, §7.7, SC-22.
- **Tasks:** watchdogs and health checks; safe mode; offline behavior review; "Hey Ace, run diagnostics"; local crash dumps; log viewer; AEC-based barge-in.
- **Acceptance criteria:**
  - [ ] An 8-hour soak test (idle + periodic commands) shows no crash and < 10 % RAM growth.
  - [ ] SC-22 passes.
  - [ ] "Hey Ace, stop" interrupts ACE mid-sentence over laptop speakers.
- **Tests:** soak script; fault tests (kill core, kill llama-server, disconnect network, unplug mic).
- **Definition of Done:** Standard.
- **[VERIFY]:** maintained AEC library for Python on Windows.
- **Pitfalls:** echo cancellation needs the exact playback signal as reference.

### S42 — UX polish + onboarding wizard
- **Goal:** A polished JARVIS HUD and a first-run experience that sets everything up.
- **Prereqs:** S41.
- **Spec:** §14 (all), §14.7.
- **Tasks:** onboarding wizard (§14.7); complete every Control Center page; animation and typography polish; accessibility checks; copy review in the persona's voice.
- **Acceptance criteria:**
  - [ ] A fresh Windows user account finishes onboarding in ≤ 15 min (excluding downloads).
  - [ ] Every Control Center page is functional; keyboard navigation works everywhere.
  - [ ] Sharan signs off on the look.
- **Tests:** UI tests for the wizard flow; accessibility lint.
- **Definition of Done:** Standard.
- **[VERIFY]:** none external.
- **Pitfalls:** polish must not add idle CPU / GPU cost (re-run the S40 idle benchmark).

### S43 — Security hardening (full pass)
- **Goal:** Close every known security gap before release.
- **Prereqs:** S42.
- **Spec:** §15 (all), D-19.
- **Tasks:** complete the §15.6 checklist; write the full STRIDE threat model into §15.2; fix all high / critical findings.
- **Acceptance criteria:**
  - [ ] Every §15.6 item is checked.
  - [ ] Zero open high / critical findings.
- **Tests:** the abuse / fuzz / injection suites become part of CI where possible.
- **Definition of Done:** Standard.
- **[VERIFY]:** current versions of the audit tools.
- **Pitfalls:** don't "fix" findings by disabling checks.

### S44 — Packaging, updates, portability
- **Goal:** ACE installs, updates and moves like proper software.
- **Prereqs:** S43.
- **Spec:** §13.6, D-22, FR-CORE-5, FR-DIST-1.
- **Tasks:** freeze the core (PyInstaller vs Nuitka — decide based on size, startup and antivirus false positives; record in §4); Tauri NSIS per-user installer; portable zip; first-run model download; signed auto-updates via GitHub Releases; uninstall cleanup (keeps user data unless chosen); `.acepack` export / import; release workflow in CI.
- **Acceptance criteria:**
  - [ ] Install on a second Windows 11 PC (or a clean user account / VM) without dev tools → onboarding → SC-01 / SC-02 work.
  - [ ] Updating from vN to vN+1 keeps data and settings.
  - [ ] Portable mode runs from a folder and writes nothing to `%LOCALAPPDATA%`.
  - [ ] Export on PC A → import on PC B restores preferences, routines, contacts and notes.
- **Tests:** installer smoke test in CI where possible; export / import round-trip.
- **Definition of Done:** Standard.
- **[VERIFY]:** Tauri bundler / updater configuration; freezing tool behavior with CUDA libraries.
- **Pitfalls:** unsigned executables trigger SmartScreen / antivirus — plan for S45 signing.

### S45 — Open-source release v1.0 → M6
- **Goal:** ACE v1.0 is public, documented and safe to install.
- **Prereqs:** S44.
- **Spec:** FR-DIST-2, NFR-8, §6.4.
- **Tasks:** make the GitHub repo public; full README (features, screenshots, setup, privacy, ToS notes), CONTRIBUTING, CODE_OF_CONDUCT, SECURITY.md, THIRD_PARTY_NOTICES (every dependency, model and voice with license + attribution), issue / PR templates; reproducible release workflow; code signing through a free open-source program if accepted (e.g. SignPath Foundation [VERIFY]); tag `v1.0.0`.
- **Acceptance criteria (M6):**
  - [ ] Release artifacts build reproducibly in CI.
  - [ ] The license audit passes (no NC / GPL components shipped).
  - [ ] A new user can install and onboard from the README alone.
- **Tests:** CI release pipeline dry run.
- **Definition of Done:** Standard + M6 sign-off by Sharan.
- **[VERIFY]:** free code-signing program availability and requirements.
- **Pitfalls:** don't publish any personal data, recordings or fixture pages that contain real accounts.

---

## §19 Packaging & distribution (summary)
- **Installer:** Tauri NSIS bundle, per-user install, no admin rights (D-22).
- **Portable:** zip with an `ace-portable.flag`; all data under `<app folder>\data` (§5.8).
- **Models:** never bundled; downloaded at onboarding into the chosen models dir with SHA-256 verification (§7.8).
- **Core executable:** frozen Python (PyInstaller or Nuitka — decided at S44).
- **Browser extension:** shipped as a zip / folder to "Load unpacked" (free). Publishing to the Chrome Web Store is optional (one-time developer fee) and never required.
- **Updates:** signed Tauri updater artifacts on GitHub Releases.
- **Moving to another PC:** install → onboarding → import `.acepack` (§13.6). API keys and tokens are re-entered (never exported).
- **Signing:** free open-source code-signing program if accepted (S45); until then, SmartScreen warnings are expected and documented in the README.

---

## §20 Risks

| ID | Risk | Likelihood / impact | Mitigation |
|---|---|---|---|
| R-1 | Websites / apps flag or ban accounts for automation (Gemini, Claude, ChatGPT, Instagram, WhatsApp) | Medium / High | Per-site opt-in with ToS notice (D-07), only on Sharan's command, human pace, caps, no bulk, confirmations, per-adapter kill switch |
| R-2 | Free AI tiers shrink or disappear | High / Medium | Provider pool + failover, local LLM fallback, config-driven provider list, quota tracker, [VERIFY] at every related stage |
| R-3 | Website UI changes break adapters | High / Medium | Versioned selectors with fallbacks, self-tests, clear `SITE_CHANGED` reports, selectors updatable without rebuilding the core |
| R-4 | Disk space runs out | High (now) / High | Everything on E:, pnpm shared store, model manager free-space checks, S00 disk targets |
| R-5 | 6 GB VRAM contention (STT + LLM + TTS + games) | Medium / Medium | VRAM budget + priorities, CPU fallbacks, game-mode unloading |
| R-6 | False wakes from videos, calls, music | Medium / Medium | Custom model tuned on Sharan's environment, two-stage acceptance, sensitivity slider, T2 confirmations |
| R-7 | Hinglish recognition accuracy | Medium / Medium | S10 benchmark on Sharan's voice, Hinglish fine-tunes, vocabulary hints, "did you say …?" |
| R-8 | Antivirus / SmartScreen false positives (input injection, frozen Python) | Medium / Medium | Code signing, Nuitka option, documented exclusions, open source |
| R-9 | Prompt injection from web pages / emails / messages | Medium / High | §15.4 policy, capability scoping, confirmations, abuse test suite |
| R-10 | Windows / app updates change UI Automation trees | Medium / Medium | OS adapters behind interfaces, rule checks, `windows_ui` regression tests |
| R-11 | Chrome MV3 service-worker suspension drops the bridge | Medium / Medium | Native-messaging keep-alive, heartbeat, auto-reconnect |
| R-12 | Spotify API policy changes again | Medium / Low | SMTC + URI fallback |
| R-13 | Council latency annoys in daily use | Medium / Low | Modes, local verifier, Balanced uses AI verifiers only on state-changing steps |
| R-14 | AI builder drifts or hallucinates APIs | High / High | §0 rules, [VERIFY] tags, small stages, Progress Log, tests, Sharan's approval gate per stage |
| R-15 | Laptop speakers + mic make barge-in hard | High / Low | Half-duplex in v1; AEC at S41 |
| R-16 | The Claude desktop sandbox hides AppData / HKCU writes made from its shells (env vars, registry keys, app data) | High / Medium | §17.4 sandbox rules; `tools/dev/set-dev-env.ps1`; system-visible items registered by ACE itself; integration tested outside Claude |

---

## §21 Parked ideas (not to be built unless Sharan asks)
- Teach-by-demonstration (record a workflow once, ACE repeats it).
- Daily dev briefing (GitHub notifications, calendar, weather).
- Clipboard history search by voice.
- Remote control from the phone (e.g. a Telegram bot or ntfy commands).
- Local vision-language model for fully offline screen understanding.
- Speaker verification (only Sharan's voice can trigger T1+ actions).
- Edge / Brave support for the bridge (same extension).
- Google Calendar sync for reminders.
- Discord integration.
- macOS / Linux ports.
- Android companion app.
- Emotion / paralinguistic tags in TTS replies.
- Hindi spoken replies.

---

## §22 Glossary

| Term | Meaning |
|---|---|
| Adapter | A module that knows how to operate one website or app (§11.6) |
| AEC | Acoustic echo cancellation — removes ACE's own voice from the mic signal |
| AUMID | Application User Model ID — how Windows identifies Store apps |
| `authuser` | Google URL parameter that selects which signed-in account a page uses |
| Council | The verification system: Supervisor + Rule Checker + verifier LLMs (§9) |
| CDP | Chrome DevTools Protocol |
| Fast path | Deterministic command handling without an LLM (§8.1) |
| FTS5 | SQLite full-text search extension |
| GGUF | Model file format used by llama.cpp |
| MCP | Model Context Protocol — a standard for connecting AI agents to tools |
| MV3 | Chrome extension Manifest Version 3 |
| Native Messaging | Chrome's mechanism for an extension to talk to a local program via stdio |
| ntfy | Free, open-source push-notification service and app |
| PKCE | OAuth flow for apps that can't keep a client secret |
| SMTC | System Media Transport Controls — Windows' global media controls |
| STT / TTS | Speech-to-text / text-to-speech |
| Supervisor | Deterministic code that enforces tiers, scope and budgets (§9.1) |
| UIA | Windows UI Automation (accessibility API used to read and control apps) |
| VAD | Voice activity detection |
| WAL | SQLite write-ahead logging mode |
| WER | Word error rate (STT accuracy metric) |

---

## §23 Progress Log (append-only; newest at the bottom)

Template for every entry:
```
### PL-NNNN — YYYY-MM-DD — <stage ID> — <short title>
- Done:
- Not done / known issues:
- [VERIFY] results (item → confirmed/changed, source, date):
- New dependencies (name, version, license):
- Decisions added/changed (with Sharan's approval):
- Tests: <commands run> → <result>
- Next step:
```

### PL-0001 — 2026-11-06 — (planning) — Master plan created
- Done: requirements gathered from Sharan in a 6-round Q&A; PC inspected (hardware, disks, installed tools, browsers, Spotify); current free voice / AI options researched; this document written.
- Not done / known issues: no code, no git repository, no installs yet. Disk space is below the S00 targets (C: 14 GB, E: 22 GB free at detection).
- [VERIFY] results: see §24 for the facts checked on 2026-11-06. Everything tagged [VERIFY] elsewhere is still open.
- New dependencies: none.
- Decisions added: D-01 … D-40 (§4).
- Tests: none (documentation only).
- Next step: S00 — [USER-ACTION] free disk space, then workspace & repository setup.

### PL-0002 — 2026-11-06 — S00 — Workspace & repository setup
- Done:
  - Disk: cleared old npm / pip / uv caches on C: (~10.6 GB, with Sharan's OK). After setup: C: 23.4 GB free, E: 193.2 GB free (S00 targets met).
  - Toolchain installed on E: per Sharan ("do everything in E, not C") — §17.4: Windows 11 SDK (standalone, installed before the Build Tools so they reuse it), VS 2022 Build Tools, Rust via rustup (installer SHA-256 verified), pnpm via npm, uv-managed CPython 3.12.16, pre-commit via `uv tool`. Caches redirected to E: (user env vars, `npm config`, `pnpm config`).
  - Repo: `git init -b main`; `.gitignore`, `.gitattributes`, `.editorconfig`, `LICENSE` (Apache-2.0 text from apache.org), `README.md`, `CLAUDE.md`; pnpm workspace root (`package.json`, `pnpm-workspace.yaml`, `eslint.config.js`, `.prettierrc.json`, `.prettierignore`).
  - Scaffolds: `core/` (uv project `ace-core`, src layout, ruff + strict mypy + pytest with `hardware` / `windows_ui` markers); `apps/desktop` (create-tauri-app `react-ts`, identifier per D-41, productName "ACE", Vitest); `apps/bridge-extension` (MV3 skeleton with no permissions yet, Vite 8 build, Vitest); `tools/dev/set-dev-env.ps1`; `tools/dev/check_plan.py` (this doc's consistency checker).
  - Quality gates (D-44): `.pre-commit-config.yaml` (15 hooks) + `.secrets.baseline`; `.github/workflows/ci.yml` (core / web / shell jobs on `windows-latest`).
- Not done / known issues:
  - Nothing is committed yet — the `[S00]` commit waits for Sharan's approval.
  - CI stays inactive until the GitHub repository exists ([USER-ACTION]).
  - Claude desktop sandbox (R-16, §17.4): user-level env vars, PATH and the pnpm global store setting were written from Claude's shell, so they are visible only inside Claude until Sharan runs `tools/dev/set-dev-env.ps1` in a normal PowerShell window.
  - Helper files in Claude's temp scratchpad vanished mid-session; helpers now live in `E:\.cache\ace-setup\`.
  - npm 11.20 skips package install scripts by default; pnpm was reinstalled with `--allow-scripts=pnpm` (its own official install script).
  - First pre-commit run added missing final newlines to two template SVGs; `check-yaml` needs `--allow-multiple-documents` because pnpm 12 writes a multi-document lockfile.
- [VERIFY] results (all checked 2026-11-06):
  - Tauri 2 Windows prerequisites → confirmed: Build Tools with "Desktop development with C++", WebView2 preinstalled on Windows 11, Rust via rustup with the MSVC toolchain — https://v2.tauri.app/start/prerequisites/
  - create-tauri-app CLI → confirmed via `--help` (v4.8): `--template react-ts`, `--manager pnpm`, `--identifier`, `--yes`.
  - pnpm install method on Windows → npm is recommended; current major is 12 — https://pnpm.io/installation. Corepack is not bundled with Node 26.
  - Latest Python 3.12 patch → 3.12.16 (uv-managed build; the system 3.12.10 is untouched).
  - Node LTS status → v26.13.0 is LTS "Lithium" (`process.release.lts`).
  - Also checked: Build Tools component IDs — https://learn.microsoft.com/en-us/visualstudio/install/workload-component-id-vs-build-tools ; rustup's MSVC prerequisites cover VS 2022 — https://rust-lang.github.io/rustup/installation/windows-msvc.html ; Vite 8 uses `build.rolldownOptions` (`rollupOptions` deprecated) and typescript-eslint's `config()` is deprecated in favour of ESLint's `defineConfig()` (installed type definitions); MSIX flexible-virtualization rules — https://learn.microsoft.com/en-us/windows/msix/desktop/flexible-virtualization
- Toolchain versions:

| Tool | Version |
|---|---|
| Windows 11 SDK | 10.0.26100.7705 (libs 10.0.26100.0) |
| VS 2022 Build Tools / MSVC | 17.14.44 / 14.44.35207 |
| Rust (rustc, cargo) / rustup | 1.99.1 / 1.29.3 |
| Python (core venv) / uv | 3.12.16 / 0.13.6 |
| Node / npm / pnpm | 26.13.0 (LTS) / 11.20.0 / 12.18.0 |
| git / pre-commit | 2.56.0 / 4.7.0 |
| Tauri crate / Tauri CLI + JS API | 2.12.5 / 2.12.4 |
| React / TypeScript / Vite / Vitest | 19.3.1 / 6.0.3 / 8.3.6 / 5.1.0 |
| ESLint / typescript-eslint / Prettier | 10.14.0 / 8.72.1 / 3.9.10 |
| ruff / mypy / pytest | 0.17.4 / 2.4.1 / 9.2.0 |

- New dependencies (licenses compatible with Apache-2.0): dev-time — ruff (MIT), mypy (MIT), pytest (MIT), pre-commit (MIT), pre-commit-hooks (MIT), detect-secrets (Apache-2.0), ESLint + @eslint/js (MIT), typescript-eslint (MIT), eslint-plugin-react-hooks (MIT), globals (MIT), Prettier (MIT), TypeScript (Apache-2.0), Vite (MIT), Vitest (MIT), @vitejs/plugin-react (MIT), @types/chrome (MIT); runtime (from the Tauri template) — React / react-dom (MIT), @tauri-apps/api, plugin-opener, CLI and the `tauri` crates (Apache-2.0 OR MIT).
- Decisions added: D-41 (app identifier, chosen by Sharan), D-42 (toolchain on E:), D-43 (workspace layout), D-44 (quality gates). Risk R-16 and the §17.4 sandbox rules added.
- Tests: `uv run pytest` → 2 passed · `ruff check`, `ruff format --check`, `mypy` (strict) → clean · `pnpm lint`, `pnpm format:check`, `pnpm typecheck` → clean · `pnpm test` → 2 passed · `pnpm build` → extension `dist/` (manifest.json + service-worker.js) and desktop UI built · `cargo fmt --check`, `cargo clippy --all-targets -- -D warnings`, `cargo test` → clean · `pre-commit run --all-files` → 15/15 passed · `pnpm tauri dev` → window "ACE" opened, then closed cleanly · inside Claude's shells `cargo` resolves to `E:\.toolchains\cargo\bin\cargo.exe` and `uv cache dir` is `E:\.cache\uv` · `python tools/dev/check_plan.py` → all checks passed.
- Next step: [USER-ACTION] Sharan runs `tools/dev/set-dev-env.ps1`, reviews S00 and approves → `[S00]` commit → S01 (core service skeleton).
- Approval: Sharan approved S00 on 2026-11-06 → committed as `[S00] Workspace and repository setup` on branch `stage/s00-workspace`; S01 continues on `stage/s01-core-service`.

---

## §24 References (facts used in this doc; checked 2026-11-06)

| Fact | Source |
|---|---|
| Chrome 136+ ignores `--remote-debugging-port` / `--remote-debugging-pipe` for the default user-data directory | https://developer.chrome.com/blog/remote-debugging-port |
| Spotify Dev Mode: owner needs Premium; new-app limits; search `limit` max 10; `/me/playlists`; changes from Feb 2026 | https://developer.spotify.com/documentation/web-api/tutorials/february-2026-migration-guide |
| Spotify redirect URIs: HTTPS except loopback; use `127.0.0.1` / `[::1]`; `localhost` not allowed; dynamic loopback ports allowed | https://developer.spotify.com/documentation/web-api/concepts/redirect_uri |
| GitHub Models retired on 2026-07-30 | https://docs.github.com/en/github-models/use-github-models/prototyping-with-ai-models |
| OpenRouter `:free` limits: 20 req/min; 50 req/day (< 10 credits purchased) or 1,000 req/day (≥ 10 credits) | https://openrouter.ai/docs/api-reference/limits |
| Groq rate limits per model (page shows Developer-plan base limits; free-plan values in account settings) | https://console.groq.com/docs/rate-limits |
| Gemini API free tier limited to Flash / Flash-Lite models; limits vary by model and project | Secondary sources (e.g. https://klymentiev.com/blog/gemini-api-free-tier); confirm at https://aistudio.google.com/rate-limit [VERIFY] |
| Windows 11 native MCP: on-device agent registry, File Explorer & Settings agent connectors (preview) | https://www.theregister.com/2025/12/08/microsoft_windows_insiders_agentic_future/ (secondary) [VERIFY] |
| Parakeet TDT v3 vs Whisper large-v3-turbo (speed, languages) | https://openwhispr.com/zh-TW/blog/parakeet-vs-whisper-vs-nemotron (secondary) |
| Kokoro-82M, Chatterbox-Turbo, Qwen3-TTS comparison (sizes, licenses, cloning) | https://localaimaster.com/blog/kokoro-vs-xtts-vs-chatterbox (secondary) [VERIFY licenses on official model cards] |
| openWakeWord-based alternatives (custom wake-word training) | https://pypi.org/project/livekit-wakeword/ , https://pypi.org/project/violawake/ (secondary) |

Secondary sources are marked; anything not confirmed by an official source stays [VERIFY] until the related stage checks it.

*End of document.*
