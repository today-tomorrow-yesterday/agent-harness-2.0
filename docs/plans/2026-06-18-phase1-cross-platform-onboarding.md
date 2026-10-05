# Phase 1: Cross-Platform Core + Claude-Guided Onboarding — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the harness clone-and-run on macOS / Linux / Windows, set up by a Claude-guided `/onboard` flow, with no Windows-only step.

**Architecture:** A new cross-platform Python config helper edits the user's Claude Code config (MCP + hooks) idempotently and BOM-free. A new `/onboard` skill orchestrates: preflight → deps → brain init → wire MCP/hooks → identity interview → verify. A portability pass removes Windows-only assumptions from the existing Python core. `ONBOARDING.md` is the human entry point.

**Tech Stack:** Python 3.10+ (`pathlib`, `json`, `platform`, `argparse`), `pytest`, existing `claude-brain` (PyYAML/mcp/sentence-transformers), Claude Code skills (Markdown).

---

## File Structure

- **Create** `bin/configure_claude.py` — locate + idempotently edit Claude Code config (`~/.claude.json`): add MCP servers + hooks; no-BOM writes; `--dry-run`. Single responsibility: config mutation.
- **Create** `bin/tests/test_configure_claude.py` — unit tests (tmp-file based, no real config touched).
- **Create** `skills/onboard/SKILL.md` — the `/onboard` orchestrator (prose instructions Claude follows).
- **Create** `ONBOARDING.md` (repo root) — one-screen entry point.
- **Modify** `claude-brain/hooks/*.py`, `claude-brain/scripts/brain-setup.py` — replace Windows-only assumptions (`\\`, `python.exe`, drive letters, `%USERPROFILE%`) with `pathlib`/`platform`.
- **Modify** `claude-brain/install.sh` — already deprecated; repoint its message to `ONBOARDING.md`.
- **Modify** `README.md` — add "Use this template / clone → /onboard" note.

---

## Task 1: Cross-platform config-file locator

**Files:**
- Create: `bin/configure_claude.py`
- Test: `bin/tests/test_configure_claude.py`

- [ ] **Step 1: Write the failing test**

```python
# bin/tests/test_configure_claude.py
import json, os, importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "configure_claude", Path(__file__).resolve().parents[1] / "configure_claude.py")
cc = importlib.util.module_from_spec(spec); spec.loader.exec_module(cc)

def test_locate_config_prefers_env_override(tmp_path, monkeypatch):
    cfg = tmp_path / "custom.json"; cfg.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_CONFIG_PATH", str(cfg))
    assert cc.locate_config() == cfg

def test_locate_config_defaults_to_home(tmp_path, monkeypatch):
    monkeypatch.delenv("CLAUDE_CONFIG_PATH", raising=False)
    monkeypatch.setattr(cc.Path, "home", staticmethod(lambda: tmp_path))
    assert cc.locate_config() == tmp_path / ".claude.json"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest bin/tests/test_configure_claude.py -v`
Expected: FAIL (module/`locate_config` not defined).

- [ ] **Step 3: Write minimal implementation**

```python
# bin/configure_claude.py
"""Cross-platform, idempotent, BOM-free editor for the Claude Code config
(~/.claude.json): register MCP servers and hooks. Pure stdlib."""
from __future__ import annotations
import argparse, json, os, sys
from pathlib import Path

def locate_config() -> Path:
    override = os.environ.get("CLAUDE_CONFIG_PATH")
    if override:
        return Path(override)
    return Path.home() / ".claude.json"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest bin/tests/test_configure_claude.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add bin/configure_claude.py bin/tests/test_configure_claude.py
git commit -m "feat(onboard): cross-platform Claude config locator"
```

---

## Task 2: BOM-free read/write roundtrip

**Files:**
- Modify: `bin/configure_claude.py`
- Test: `bin/tests/test_configure_claude.py`

- [ ] **Step 1: Write the failing test**

```python
def test_write_config_has_no_bom_and_roundtrips(tmp_path):
    p = tmp_path / ".claude.json"
    cc.write_config(p, {"a": 1})
    raw = p.read_bytes()
    assert raw[:3] != b"\xef\xbb\xbf"          # no UTF-8 BOM
    assert cc.read_config(p) == {"a": 1}

def test_read_config_missing_returns_empty(tmp_path):
    assert cc.read_config(tmp_path / "nope.json") == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest bin/tests/test_configure_claude.py -k roundtrip -v`
Expected: FAIL (`write_config`/`read_config` not defined).

- [ ] **Step 3: Write minimal implementation**

```python
def read_config(path: Path) -> dict:
    if not Path(path).exists():
        return {}
    text = Path(path).read_text(encoding="utf-8-sig")  # tolerate an existing BOM on read
    return json.loads(text) if text.strip() else {}

def write_config(path: Path, data: dict) -> None:
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    Path(path).write_text(text, encoding="utf-8")       # utf-8 == no BOM
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest bin/tests/test_configure_claude.py -k "roundtrip or missing" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add bin/configure_claude.py bin/tests/test_configure_claude.py
git commit -m "feat(onboard): BOM-free config read/write"
```

---

## Task 3: Idempotent add_mcp_server

**Files:**
- Modify: `bin/configure_claude.py`
- Test: `bin/tests/test_configure_claude.py`

- [ ] **Step 1: Write the failing test**

```python
def test_add_mcp_server_is_idempotent():
    cfg = {}
    cc.add_mcp_server(cfg, "brain-server", "python3", ["server.py"], {})
    cc.add_mcp_server(cfg, "brain-server", "python3", ["server.py"], {})
    assert list(cfg["mcpServers"]) == ["brain-server"]
    assert cfg["mcpServers"]["brain-server"]["command"] == "python3"
    assert cfg["mcpServers"]["brain-server"]["args"] == ["server.py"]

def test_add_mcp_server_updates_existing():
    cfg = {"mcpServers": {"brain-server": {"command": "old", "args": []}}}
    cc.add_mcp_server(cfg, "brain-server", "python3", ["server.py"], {"X": "1"})
    assert cfg["mcpServers"]["brain-server"]["command"] == "python3"
    assert cfg["mcpServers"]["brain-server"]["env"] == {"X": "1"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest bin/tests/test_configure_claude.py -k mcp -v`
Expected: FAIL (`add_mcp_server` not defined).

- [ ] **Step 3: Write minimal implementation**

```python
def add_mcp_server(config: dict, name: str, command: str,
                   args: list[str], env: dict | None = None) -> dict:
    servers = config.setdefault("mcpServers", {})
    entry = {"type": "stdio", "command": command, "args": list(args)}
    if env:
        entry["env"] = dict(env)
    servers[name] = entry          # assignment == idempotent upsert by key
    return config
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest bin/tests/test_configure_claude.py -k mcp -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add bin/configure_claude.py bin/tests/test_configure_claude.py
git commit -m "feat(onboard): idempotent add_mcp_server"
```

---

## Task 4: Idempotent add_hook

**Files:**
- Modify: `bin/configure_claude.py`
- Test: `bin/tests/test_configure_claude.py`

- [ ] **Step 1: Write the failing test**

```python
def test_add_hook_idempotent():
    cfg = {}
    cc.add_hook(cfg, "Stop", "python3 hooks/stop.py")
    cc.add_hook(cfg, "Stop", "python3 hooks/stop.py")
    stop = cfg["hooks"]["Stop"]
    # exactly one matching command entry, not duplicated
    cmds = [h["command"] for grp in stop for h in grp["hooks"]]
    assert cmds.count("python3 hooks/stop.py") == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest bin/tests/test_configure_claude.py -k hook -v`
Expected: FAIL (`add_hook` not defined).

- [ ] **Step 3: Write minimal implementation**

```python
def add_hook(config: dict, event: str, command: str) -> dict:
    hooks = config.setdefault("hooks", {})
    groups = hooks.setdefault(event, [])
    for grp in groups:
        for h in grp.get("hooks", []):
            if h.get("command") == command:
                return config            # already present
    groups.append({"hooks": [{"type": "command", "command": command}]})
    return config
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest bin/tests/test_configure_claude.py -k hook -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add bin/configure_claude.py bin/tests/test_configure_claude.py
git commit -m "feat(onboard): idempotent add_hook"
```

---

## Task 5: CLI with --dry-run

**Files:**
- Modify: `bin/configure_claude.py`
- Test: `bin/tests/test_configure_claude.py`

- [ ] **Step 1: Write the failing test**

```python
def test_cli_dry_run_does_not_write(tmp_path, monkeypatch, capsys):
    cfg = tmp_path / ".claude.json"
    monkeypatch.setenv("CLAUDE_CONFIG_PATH", str(cfg))
    rc = cc.main(["add-mcp", "--name", "brain-server", "--command", "python3",
                  "--arg", "server.py", "--dry-run"])
    assert rc == 0
    assert not cfg.exists()                       # dry-run wrote nothing
    assert "brain-server" in capsys.readouterr().out

def test_cli_add_mcp_writes(tmp_path, monkeypatch):
    cfg = tmp_path / ".claude.json"
    monkeypatch.setenv("CLAUDE_CONFIG_PATH", str(cfg))
    rc = cc.main(["add-mcp", "--name", "brain-server", "--command", "python3",
                  "--arg", "server.py"])
    assert rc == 0
    assert cc.read_config(cfg)["mcpServers"]["brain-server"]["command"] == "python3"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest bin/tests/test_configure_claude.py -k cli -v`
Expected: FAIL (`main` not defined).

- [ ] **Step 3: Write minimal implementation**

```python
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Edit Claude Code config (MCP/hooks).")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("add-mcp")
    p.add_argument("--name", required=True); p.add_argument("--command", required=True)
    p.add_argument("--arg", action="append", default=[], dest="args")
    p.add_argument("--env", action="append", default=[], help="KEY=VALUE")
    p.add_argument("--dry-run", action="store_true")
    h = sub.add_parser("add-hook")
    h.add_argument("--event", required=True); h.add_argument("--command", required=True)
    h.add_argument("--dry-run", action="store_true")
    ns = parser.parse_args(argv)
    path = locate_config(); config = read_config(path)
    if ns.cmd == "add-mcp":
        env = dict(kv.split("=", 1) for kv in ns.env)
        add_mcp_server(config, ns.name, ns.command, ns.args, env)
    elif ns.cmd == "add-hook":
        add_hook(config, ns.event, ns.command)
    if ns.dry_run:
        print(json.dumps(config, indent=2)); return 0
    write_config(path, config); print(f"Updated {path}"); return 0

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run full suite**

Run: `python -m pytest bin/tests/test_configure_claude.py -v`
Expected: PASS (all). Also run the existing suite: `python -m pytest bin/tests/ -q` — Expected: still green.

- [ ] **Step 5: Commit**

```bash
git add bin/configure_claude.py bin/tests/test_configure_claude.py
git commit -m "feat(onboard): config-helper CLI with --dry-run"
```

---

## Task 6: Portability audit + fixes on the Python core

**Files:**
- Modify: `claude-brain/scripts/brain-setup.py`, `claude-brain/hooks/*.py` (only those with Windows-only assumptions)

- [ ] **Step 1: Audit** — run and record every hit:

```bash
cd <repo>
grep -rnE "\.exe\b|%USERPROFILE%|[A-Za-z]:\\\\|\\\\\\\\|os\.sep|python\.exe" claude-brain/ bin/configure_claude.py
```

- [ ] **Step 2: For each hit, apply the cross-platform replacement:**
  - `"python.exe"` / hardcoded interpreter → `sys.executable`
  - `%USERPROFILE%` / `C:\Users\...` / drive letters → `Path.home()` / `pathlib`
  - string path joins with `\\` → `Path(...) / ...`
  - shell-specific calls → `subprocess` with list args + `shutil.which(...)`

- [ ] **Step 3: Verify the core still imports + sets up on this OS**

Run: `python claude-brain/scripts/brain-setup.py --help` (or dry equivalent)
Expected: no path/interpreter errors.

- [ ] **Step 4: Run the existing test suite**

Run: `python -m pytest bin/tests/ -q`
Expected: green.

- [ ] **Step 5: Commit**

```bash
git add claude-brain/
git commit -m "fix(core): remove Windows-only path/interpreter assumptions"
```

---

## Task 7: Author the `/onboard` skill

**Files:**
- Create: `skills/onboard/SKILL.md`

- [ ] **Step 1: Write `skills/onboard/SKILL.md`** with YAML frontmatter (`name: onboard`, `description:` covering "set up / onboard this system on a new machine") and an ordered, OS-aware procedure:
  1. **Preflight:** `python -c "import platform; print(platform.system())"`; confirm Claude Code host + active subscription; check `git` and Python ≥3.10 via `shutil.which`. If a system tool is missing, print the OS-correct install hint (macOS `brew`, Debian `apt`, Windows `winget`) and stop.
  2. **Deps:** `python -m pip install -r claude-brain/requirements.txt`. Note the ~80 MB `sentence-transformers` model downloads on first search.
  3. **Init brain:** `python claude-brain/scripts/brain-setup.py`.
  4. **Wire MCP + hooks:** call `python bin/configure_claude.py add-mcp --name brain-server --command <sys.executable> --arg claude-brain/mcp/server.py` then `add-hook` for each event the brain uses (read the hook filenames in `claude-brain/hooks/` and register the ones the core requires). Use `--dry-run` first, show the user, then apply.
  5. **Identity interview:** for each BOOTSTRAP file (`memory/user.md`, `memory/soul.md`, optional `memory/agent.md`/`frame.md`, `memory/feedback/*`, `memory/projects/*`), ask the embedded questions one at a time, then write the file in the user's words and remove the BOOTSTRAP block.
  6. **Verify:** restart-or-note the MCP; run a `claude-brain` keyword search probe; confirm `CLAUDE.md` loads; print a "you're set up — here's what you can do" summary.

- [ ] **Step 2: Smoke-check** the skill file parses (valid frontmatter, no broken links): open it, confirm `name`/`description` present.

- [ ] **Step 3: Commit**

```bash
git add skills/onboard/SKILL.md
git commit -m "feat(onboard): /onboard orchestrator skill"
```

---

## Task 8: `ONBOARDING.md` + README template note + install.sh pointer

**Files:**
- Create: `ONBOARDING.md`
- Modify: `README.md`, `claude-brain/install.sh`

- [ ] **Step 1: Write `ONBOARDING.md`** — Prerequisites (Claude Code + subscription, git, Python ≥3.10); one instruction: "Open this folder in Claude Code and say *onboard me* (or run `/onboard`)."; a "Manual fallback" link to `docs/REHYDRATE.md`; a one-line "what you'll have when done."

- [ ] **Step 2: Add to `README.md`** a "Get started" section: "Use this template" (GitHub) or `git clone`, then see `ONBOARDING.md`.

- [ ] **Step 3: Repoint `claude-brain/install.sh`** message from the REHYDRATE reference to `ONBOARDING.md` (keep the `exit 1`).

- [ ] **Step 4: Commit**

```bash
git add ONBOARDING.md README.md claude-brain/install.sh
git commit -m "docs(onboard): ONBOARDING.md + template usage"
```

---

## Task 9: End-to-end dry verification on this machine

- [ ] **Step 1:** In a scratch HOME (`CLAUDE_CONFIG_PATH=$(mktemp -d)/.claude.json`), run the config-helper commands the skill issues; assert the MCP + hooks land (re-read the file).
- [ ] **Step 2:** Run `python -m pytest bin/tests/ -q` — full suite green.
- [ ] **Step 3:** Walk the `/onboard` SKILL.md steps mentally against a clean clone; confirm no step assumes Windows. Note any gaps for fix.
- [ ] **Step 4: Commit** any fixes; tag Phase 1 done in the spec status.

```bash
git add -A && git commit -m "test(onboard): phase-1 end-to-end dry verification"
```

---

## Self-Review (done at write time)

- **Spec coverage:** /onboard skill (§4.1.A) → Tasks 7,9; config helper (§4.1.B) → Tasks 1-5; ONBOARDING.md (§4.1.C) → Task 8; portability pass (§4.1.D) → Task 6; distribution/template (§4.1.E) → Task 8 (README) + a manual GitHub "template" toggle (out-of-code, noted for the owner). Success criteria (§4.2) → Task 9 + real macOS/Windows run-through (requires a colleague machine — flagged as a manual validation step, can't be automated from the author's box).
- **Placeholders:** none — all code/tests are concrete.
- **Type consistency:** `locate_config`/`read_config`/`write_config`/`add_mcp_server`/`add_hook`/`main` names consistent across tasks.
- **Known manual step:** flipping the GitHub repo to "template" and the real cross-OS run-through are human/colleague actions, not code — called out, not hidden.
