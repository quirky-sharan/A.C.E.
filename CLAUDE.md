# ACE — notes for AI agents

ACE is a Windows desktop assistant that operates Sharan's PC by voice or text (apps, Chrome tabs, AI sites, media, messages).

**Before any work:** read `ACE_MASTER_PLAN.md` — STATUS, all of §0, §4, the current stage in §18 (and the sections it links), and the last 3 entries of §23.

## Key commands
- Load toolchain env inside Claude's shells first: `. E:\.cache\ace-setup\env.ps1` (see §17.4 sandbox note)
- Core (Python, in `core/`): `uv run pytest` · `uv run ruff check .` · `uv run ruff format --check .` · `uv run mypy`
- DB schema change: edit `core/src/ace_core/db/models.py`, then add a migration as described in `core/alembic.ini`
- IPC dev client (core running, in `core/`): `uv run ace-cli health` · `uv run ace-cli call <method> '<json params>'` · `uv run ace-cli watch` · `uv run ace-cli send <command text>`
- Skills (in `core/`): registry `ace_core/skills/catalog.py` · fast-path phrases `ace_core/brain/grammar.py` + golden set `tests/golden/commands.yaml` · schema export `uv run python -m ace_core.skills.export_schema [--dev]`
- IPC schema change (`core/src/ace_core/ipc/schemas.py`, `methods.py`, `events.py`): run `pnpm gen:ipc` at the repo root and commit both generated files
- Desktop app (Tauri): `pnpm --filter ace-desktop tauri dev` — starts its own core (`uv run ace-core --dev --supervised`, D-52); quit from the tray or with `apps\desktop\src-tauri\target\debug\ace-desktop.exe --quit`
- Browser extension: `pnpm --filter ace-bridge-extension build`
- All JS/TS (repo root): `pnpm lint` · `pnpm format:check` · `pnpm typecheck` · `pnpm test`
- Hooks: `pre-commit run --all-files`

## Rules (verbatim from ACE_MASTER_PLAN.md §0.2)
- **R1 One stage at a time.** Only work on the stage named in STATUS. Do not start the next stage until the current stage's Definition of Done is met **and Sharan approves** moving on.
- **R2 Don't re-decide.** Items in §4 are decided. To change one: explain why, give options with a recommendation, get Sharan's explicit approval, then update §4 and every affected section in the same commit.
- **R3 Never guess APIs.** Before using any library, OS API, web endpoint, CSS selector, CLI flag or config key, check the official documentation for the exact pinned version. If you cannot verify it, say so and ask. Never invent function names, parameters or endpoints.
- **R4 Resolve [VERIFY] tags.** Every [VERIFY] item in the current stage must be checked against an official source before it is relied on. Record the outcome (confirmed / changed, source URL, date) in the Progress Log. If the fact changed, update this doc.
- **R5 Ask, don't assume.** If something is ambiguous, conflicting or impossible, stop and ask Sharan with concrete options and your recommendation.
- **R7 Security basics from day 1.** The §15.1 baseline is mandatory from S01 onward. Never weaken it "temporarily".
- **R8 No secrets anywhere.** Never commit or log API keys, OAuth tokens, cookies, passwords, contacts' phone numbers or emails. Secrets live only in Windows Credential Manager (via `keyring`).
