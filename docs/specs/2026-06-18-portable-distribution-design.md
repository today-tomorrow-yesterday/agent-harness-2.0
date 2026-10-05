# Portable Distribution + Claude-Guided Onboarding — Design Spec

**Date:** 2026-06-18
**Status:** ✅ ALL PHASES COMPLETE. Phase 1 (`c519b8f`) · Phase 2 + curation (`f98f5cf`, `66b05a4`) · Phase 3 gbrain + Skill-Forge + final genericization (`27d52bf`). 67 tests pass; repo clean of author paths (`<repo>`/`Z:\Clone`) and identity/client data. **Remaining = real-machine VALIDATION only** (not build): the *nix scheduler apply/remove, gbrain_setup --apply, and the full /onboard flow were authored on Windows and need one run on a real macOS/Linux box (see docs/validate-phase1.md).
**Goal:** Turn `agent-harness` from a Windows-centric personal scaffold into a **cross-platform, self-installing "Claude Code OS"** that a colleague clones, opens in Claude Code, and sets up by asking Claude to "onboard me" — adapting to macOS, Linux, or Windows.

---

## 1. Context

`agent-harness` is the public/portable fork of a private source system. It bundles four runtime layers: identity+rules (`CLAUDE.md`), source-of-truth markdown (`memory/`), searchable conversation history (`claude-brain/`, SQLite + MCP), and automation (`bin/` schedulers + skills + Skill-Forge). Today it assumes **Windows** (PowerShell scripts, Task Scheduler) and a single owner. The colleagues who will use it are on **mixed macOS / Linux / Windows** and each has (or will get) their own Claude Code subscription.

**Already cross-platform (leverage, don't rebuild):** `claude-brain` is pure-Python — hooks (`session-start/stop/...py`), `scripts/brain-setup.py`, and deps `PyYAML / mcp / sentence-transformers / numpy`. The old `claude-brain/install.sh` is deprecated.

**Windows-specific (must port):** `bin/*.ps1` schedulers, Windows Task Scheduler registration, and any hardcoded path / `python` vs `python3` assumptions in MCP + hook registration.

---

## 2. Decomposition (3 phases)

Each phase ships standalone value and gets its own implementation plan.

| Phase | Deliverable | Depends on |
|---|---|---|
| **1. Cross-platform core + onboarding** | memory + claude-brain + skills working on any OS, driven by a `/onboard` flow | — |
| **2. Cross-platform scheduled agents** | weekly-planner / daily-brief / security-watcher via a scheduler abstraction (Task Scheduler / launchd / cron) | Phase 1 |
| **3. gbrain + Skill-Forge** | local knowledge brain (3rd-party gbrain + Ollama/bun/PGLite) + self-improving loop, wired by the onboarder | Phases 1-2 |

---

## 3. Cross-cutting principles

- **Per-machine adaptation via Claude.** The onboarder detects OS at runtime and branches; this is what makes "mixed OS" tractable without N parallel installers.
- **Identity isolation.** Each colleague's `memory/` + secrets live only in their own clone. The onboarder writes their files from interview answers; it never copies the author's data.
- **Secrets never travel.** No key is ever committed or copied. `*.env` and secret patterns stay gitignored (guard already in place). The onboarder prompts each person for their own.
- **Idempotent + no-BOM config edits.** A shared Python helper edits Claude Code config (`~/.claude.json`) and any tool config; always writes UTF-8 **without BOM** (a BOM breaks JSON parsers — known failure mode).
- **Auto-install pip packages; only *instruct* for system tools.** Silent installation of Python/git/bun/Ollama across three OSes is fragile and intrusive — detect them and print the OS-correct install command instead.
- **Distribution = GitHub template repo.** Colleagues "Use this template" (or clone). The repo stays private until the owner flips it.

---

## 4. Phase 1 — Cross-platform core + Claude-guided onboarding (build-ready)

### 4.1 Components

**A. `/onboard` skill** (`skills/onboard/SKILL.md` + any helper scripts) — the orchestrator Claude executes. Ordered steps:

1. **Preflight** — detect OS (`platform.system()` / `uname`); confirm Claude Code is the host and a subscription is active; check `git` and a Python 3.10+ interpreter (`python3` or `python`). Missing system tools → print OS-specific install command and pause.
2. **Dependencies** — `pip install -r claude-brain/requirements.txt` into the user's environment (or a venv if preferred). Note: `sentence-transformers` lazily downloads a ~80 MB model on first search; flag this.
3. **Initialize brain** — run `claude-brain/scripts/brain-setup.py` (creates the SQLite DB + schema in the per-user data dir).
4. **Register MCP + hooks** — via a new **config helper** (4.1.B): add the `brain-server` MCP entry and the session hooks (`session-start`, `stop`, etc.) to the user's Claude Code config, with correct absolute repo path and interpreter for their OS.
5. **Identity interview** — walk the existing `BOOTSTRAP` sections: `memory/user.md`, `memory/soul.md`, optional `memory/agent.md` + `memory/frame.md`, `memory/feedback/*` rules, `memory/projects/*` briefs. Ask the bootstrap questions conversationally; write each file in the colleague's own words; delete the BOOTSTRAP block afterward.
6. **Verify** — index a probe and run a `claude-brain` search; confirm `CLAUDE.md` + memory load and that a hook fires; print a status summary + "what you can do now."

**B. Config helper** (`bin/configure_claude.py`, cross-platform) — idempotent, no-BOM editor for `~/.claude.json` (and `~/.claude-<profile>/.claude.json` where relevant). Functions: `add_mcp_server(name, command, args, env)`, `add_hook(event, command)`, with OS-aware path + interpreter resolution. Pure Python, no PowerShell.

**C. `ONBOARDING.md`** (repo root) — one screen: prerequisites (Claude Code + subscription, git, Python 3.10+), then "Open this folder in Claude Code and say *onboard me* (or run `/onboard`)." Points at the skill; links REHYDRATE.md for manual fallback.

**D. Portability pass** — audit `claude-brain` hooks, `brain-setup.py`, and `scripts/*.py` for Windows-only assumptions (path separators, `python.exe`, `%USERPROFILE%`, drive letters); replace with `pathlib` + `os`/`sys`/`platform`. Remove the dead `install.sh` (or convert to a thin pointer to ONBOARDING.md).

**E. Distribution** — enable GitHub "template repository"; add a short "Use this template / clone" note to README + ONBOARDING.md.

### 4.2 Success criteria
A colleague on **macOS** and one on **Windows** each: clone → open in Claude Code → `/onboard` → answer the interview → finish with (a) memory that personalizes Claude, (b) `brain-server` MCP connected and search returning results, (c) session hooks capturing new conversations — with **no Windows-only step**.

### 4.3 Out of scope (Phase 1)
Schedulers (Phase 2); gbrain + Skill-Forge (Phase 3).

---

## 5. Phase 2 — Cross-platform scheduled agents (design)

**Problem:** automation (`weekly-planner.py`, `daily-brief.py`, the AgentShield watcher) is registered via Windows Task Scheduler / PowerShell only.

**Design:** one **job registry** (`bin/scheduler/jobs.py`) declaring each job (id, command, cadence, time) once, plus three thin **OS backends** that install/remove native entries from that declaration:
- Windows → Task Scheduler (`schtasks` / PowerShell `Register-ScheduledTask`)
- macOS → `launchd` (`~/Library/LaunchAgents/*.plist` + `launchctl`)
- Linux → `cron` (user crontab) or systemd-user timers (cron as the portable default)

A `bin/scheduler/install.py` reads the registry, detects OS, and lays down the right entries idempotently; `uninstall.py` removes them. The job *logic* stays the existing Python; only registration is OS-specific. The `/onboard` skill calls `install.py` as an opt-in step ("enable background agents?").

**Success:** the same job set runs on a schedule on all three OSes, installed/removed by one command, no PowerShell dependency on non-Windows.

**Open question (resolve in Phase 2 spec):** the schedulers invoke `claude -p` — confirm headless invocation + auth works identically on macOS/Linux (it should; it's the same CLI).

---

## 6. Phase 3 — gbrain + Skill-Forge (design)

**gbrain** (local knowledge brain over the user's own docs):
- It is a **third-party tool** (`garrytan/gbrain`) — **referenced, not bundled**. The onboarder offers to clone it and `bun install`.
- Dependencies the onboarder installs/guides: **bun** runtime, **Ollama** + `nomic-embed-text` (keyless local embeddings), PGLite (bundled with gbrain).
- Wire the gbrain MCP into Claude Code config (reuse the 4.1.B helper). Provide genericized `gbrain-sync` + `gbrain-ingest-code` glue scripts (ported off PowerShell to Python or per-OS) pointing at the user's own content dir, not `Z:\Clone`.
- **Carry forward known gotchas:** PGLite is single-writer (one `gbrain serve` at a time — a session's MCP holds the lock); `gbrain import` is markdown-only while `gbrain sync --strategy code` builds the code graph; never write the gbrain config with a BOM.

**Skill-Forge** (`bin/skill_forge/`): already Python; mostly needs a portability pass + a documented opt-in invocation (and, if desired, a Phase-2 scheduled job).

**Success:** a technical colleague can opt into gbrain during onboarding and end with a queryable local brain over their own docs/code; Skill-Forge runs on any OS.

---

## 7. Testing strategy

- **Phase 1:** real run-throughs on at least one macOS and one Windows machine (and Linux if available). Automated: a `--dry-run` mode on the config helper + a smoke test that asserts MCP entry written, DB created, a search returns.
- **Phases 2-3:** per-OS install/uninstall verification (entry appears in the native scheduler; job fires once on-demand); gbrain handshake test post-wiring.
- Keep the existing `claude-brain` test suite green throughout (44 tests).

## 8. Risks / open questions

- **Can't fully self-test other OSes from the author's Windows machine** — launchd/cron paths need a real macOS/Linux run (or a colleague to validate). Mitigate with dry-run + clear verification steps.
- **Headless `claude -p` parity** across OSes (Phase 2) — expected fine, verify.
- **Dependency heaviness** (Phase 3: bun + Ollama + model download) — keep gbrain a clearly-optional onboarding branch.
- **Claude Code config location/shape** may vary by version/platform — the config helper must locate it robustly and fail loudly if it can't.

## 9. Non-goals
- No rewrite of `claude-brain`'s core. No new features beyond porting + onboarding. No bundling of third-party tools. No cloud component — everything stays local to each colleague's machine, on their own subscription.
