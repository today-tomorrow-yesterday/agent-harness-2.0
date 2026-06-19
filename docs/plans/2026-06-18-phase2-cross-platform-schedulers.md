# Phase 2: Cross-Platform Scheduled Agents — Implementation Plan

> **For agentic workers:** implement task-by-task; steps use `- [ ]`. Design: see spec §5.

**Goal:** register the harness's background jobs (weekly-planner, daily-brief, security-watcher) on a schedule across Windows / macOS / Linux from one declarative job registry.

**Architecture:** A declarative `Job` registry (`bin/scheduler/jobs.py`); pure per-OS **generators** (`backends.py`) that turn a `Job` into a cron line / launchd plist / schtasks command (unit-testable on any OS); an `install.py` that detects the OS, generates entries, and applies/removes them idempotently with `--dry-run`. Job scripts are invoked **repo-relative** (no hardcoded author paths).

**Tech Stack:** Python 3.10+ stdlib (`dataclasses`, `platform`, `pathlib`, `plistlib`, `subprocess`), `pytest`.

---

## File Structure
- **Create** `bin/scheduler/__init__.py`
- **Create** `bin/scheduler/backends.py` — pure generators: `to_cron_line`, `to_launchd_plist`, `to_schtasks_cmd` (+ DOW maps). No side effects.
- **Create** `bin/scheduler/jobs.py` — `Job` dataclass + `REGISTRY` (the harness's jobs) + `repo_root()`.
- **Create** `bin/scheduler/install.py` — `detect_os()`, `plan()`, `apply()`, `remove()`, CLI `--dry-run`.
- **Create** `bin/tests/test_scheduler.py` — TDD the generators + registry + plan.

Tasks 1-4 below cover the **provable core** (generators + registry + plan). The side-effectful `apply()`/`remove()` (crontab write / launchctl load / schtasks exec) are implemented in Task 5 and flagged **needs real-machine validation** (can't be exercised from the author's Windows box for the *nix backends).

---

## Task 1: Job model + DOW maps

**Files:** Create `bin/scheduler/jobs.py`, `bin/scheduler/__init__.py`; Test `bin/tests/test_scheduler.py`

- [ ] **Step 1: failing test**
```python
import importlib.util; from pathlib import Path
def _load(name):
    p = Path(__file__).resolve().parents[1] / "scheduler" / f"{name}.py"
    s = importlib.util.spec_from_file_location(f"scheduler_{name}", p)
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
jobs = _load("jobs")
def test_job_defaults():
    j = jobs.Job(id="x", args=["bin/x.py"], cadence="daily", time="07:00")
    assert j.dow is None and j.cadence == "daily"
def test_registry_nonempty_and_repo_relative():
    assert jobs.REGISTRY and all(not a.startswith("/") and ":" not in a
                                 for j in jobs.REGISTRY for a in j.args)
```
- [ ] **Step 2: run → FAIL** `python -m pytest bin/tests/test_scheduler.py -k job -v`
- [ ] **Step 3: implement** `bin/scheduler/__init__.py` (empty) and `jobs.py`:
```python
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

@dataclass
class Job:
    id: str
    args: list[str]        # argv relative to repo root, e.g. ["bin/daily-brief.py"]
    cadence: str           # "daily" | "weekly"
    time: str              # "HH:MM" 24h
    dow: str | None = None # weekly only: MON..SUN

def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]

REGISTRY: list[Job] = [
    Job("daily-brief",    ["bin/daily-brief.py"],    "daily",  "07:00"),
    Job("weekly-planner", ["bin/weekly-planner.py"], "weekly", "09:00", dow="SUN"),
]
```
- [ ] **Step 4: run → PASS**
- [ ] **Step 5: commit** `feat(sched): job model + registry`

---

## Task 2: cron generator

**Files:** Create `bin/scheduler/backends.py`; Test same

- [ ] **Step 1: failing test**
```python
backends = _load("backends")
def test_cron_daily():
    j = jobs.Job("daily-brief", ["bin/daily-brief.py"], "daily", "07:00")
    line = backends.to_cron_line(j, python="/usr/bin/python3", repo="/home/u/ah")
    assert line.startswith("0 7 * * * ")
    assert "cd /home/u/ah && /usr/bin/python3 bin/daily-brief.py" in line
def test_cron_weekly_sunday():
    j = jobs.Job("wp", ["bin/weekly-planner.py"], "weekly", "09:00", dow="SUN")
    assert backends.to_cron_line(j, "/usr/bin/python3", "/r").startswith("0 9 * * 0 ")
```
- [ ] **Step 2: run → FAIL**
- [ ] **Step 3: implement** in `backends.py`:
```python
from __future__ import annotations
import plistlib

_CRON_DOW = {"SUN":0,"MON":1,"TUE":2,"WED":3,"THU":4,"FRI":5,"SAT":6}

def _hm(t: str) -> tuple[int,int]:
    h, m = t.split(":"); return int(h), int(m)

def to_cron_line(job, python: str, repo: str) -> str:
    h, m = _hm(job.time)
    dow = _CRON_DOW[job.dow] if job.cadence == "weekly" else "*"
    cmd = " ".join([python, *job.args])
    return f"{m} {h} * * {dow} cd {repo} && {cmd}  # agent-harness:{job.id}"
```
- [ ] **Step 4: run → PASS**
- [ ] **Step 5: commit** `feat(sched): cron generator`

---

## Task 3: launchd + schtasks generators

**Files:** Modify `bin/scheduler/backends.py`; Test same

- [ ] **Step 1: failing test**
```python
def test_launchd_plist():
    j = jobs.Job("wp", ["bin/weekly-planner.py"], "weekly", "09:00", dow="SUN")
    xml = backends.to_launchd_plist(j, "/usr/bin/python3", "/r")
    import plistlib; d = plistlib.loads(xml.encode())
    assert d["Label"] == "agent-harness.wp"
    assert d["ProgramArguments"] == ["/usr/bin/python3", "/r/bin/weekly-planner.py"]
    assert d["StartCalendarInterval"]["Hour"] == 9
    assert d["StartCalendarInterval"]["Minute"] == 0
    assert d["StartCalendarInterval"]["Weekday"] == 0
def test_schtasks_cmd():
    j = jobs.Job("wp", ["bin/weekly-planner.py"], "weekly", "09:00", dow="SUN")
    cmd = backends.to_schtasks_cmd(j, "python", r"C:\r")
    assert cmd[:3] == ["schtasks", "/Create", "/SC"]
    assert "WEEKLY" in cmd and "/D" in cmd and "SUN" in cmd
    assert "09:00" in cmd
```
- [ ] **Step 2: run → FAIL**
- [ ] **Step 3: implement** appended to `backends.py`:
```python
def to_launchd_plist(job, python: str, repo: str) -> str:
    h, m = _hm(job.time)
    sci = {"Hour": h, "Minute": m}
    if job.cadence == "weekly":
        sci["Weekday"] = _CRON_DOW[job.dow]      # launchd: 0/7=Sun
    d = {
        "Label": f"agent-harness.{job.id}",
        "ProgramArguments": [python, *[f"{repo}/{a}" for a in job.args]],
        "StartCalendarInterval": sci,
        "RunAtLoad": False,
    }
    return plistlib.dumps(d).decode()

def to_schtasks_cmd(job, python: str, repo: str) -> list[str]:
    import os
    tr = " ".join([python, *[os.path.join(repo, a) for a in job.args]])
    cmd = ["schtasks", "/Create", "/SC"]
    if job.cadence == "weekly":
        cmd += ["WEEKLY", "/D", job.dow]
    else:
        cmd += ["DAILY"]
    cmd += ["/ST", job.time, "/TN", f"agent-harness-{job.id}", "/TR", tr, "/F"]
    return cmd
```
- [ ] **Step 4: run → PASS**
- [ ] **Step 5: commit** `feat(sched): launchd + schtasks generators`

---

## Task 4: OS detection + plan()

**Files:** Create `bin/scheduler/install.py`; Test same

- [ ] **Step 1: failing test**
```python
install = _load("install")
def test_detect_os(monkeypatch):
    monkeypatch.setattr(install.platform, "system", lambda: "Darwin")
    assert install.detect_os() == "macos"
    monkeypatch.setattr(install.platform, "system", lambda: "Linux")
    assert install.detect_os() == "linux"
    monkeypatch.setattr(install.platform, "system", lambda: "Windows")
    assert install.detect_os() == "windows"
def test_plan_returns_one_artifact_per_job():
    p = install.plan(os_name="linux", python="/usr/bin/python3", repo="/r")
    assert len(p) == len(jobs.REGISTRY)
    assert all(isinstance(x, str) and "agent-harness:" in x for x in p)  # cron lines
```
- [ ] **Step 2: run → FAIL**
- [ ] **Step 3: implement** `install.py`:
```python
from __future__ import annotations
import argparse, platform, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import jobs as _jobs, backends as _be

def detect_os(name: str | None = None) -> str:
    s = (name or platform.system()).lower()
    return {"darwin": "macos", "linux": "linux", "windows": "windows"}.get(s, s)

def plan(os_name: str, python: str, repo: str) -> list:
    out = []
    for j in _jobs.REGISTRY:
        if os_name == "linux":   out.append(_be.to_cron_line(j, python, repo))
        elif os_name == "macos": out.append(_be.to_launchd_plist(j, python, repo))
        elif os_name == "windows": out.append(" ".join(_be.to_schtasks_cmd(j, python, repo)))
    return out

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Install harness scheduled jobs.")
    ap.add_argument("--dry-run", action="store_true")
    ns = ap.parse_args(argv)
    os_name = detect_os(); python = sys.executable; repo = str(_jobs.repo_root())
    artifacts = plan(os_name, python, repo)
    if ns.dry_run:
        print(f"# OS={os_name}\n" + "\n---\n".join(artifacts)); return 0
    print("Real install requires the OS backend (Task 5)."); return 0

if __name__ == "__main__":
    sys.exit(main())
```
- [ ] **Step 4: run → PASS**; then full suite `python -m pytest -q` green.
- [ ] **Step 5: commit** `feat(sched): OS detection + plan + dry-run CLI`

---

## Task 5: Side-effectful apply()/remove() (flagged: needs real-machine validation)

**Files:** Modify `bin/scheduler/install.py`

- [ ] Implement `apply(os_name, ...)` and `remove(os_name, ...)`:
  - **linux:** read user crontab (`crontab -l`), strip prior `# agent-harness:<id>` lines, append new ones, `crontab -` ; remove = strip lines.
  - **macos:** write `~/Library/LaunchAgents/agent-harness.<id>.plist`, `launchctl load -w`; remove = `launchctl unload` + delete file.
  - **windows:** run the `to_schtasks_cmd` list via `subprocess`; remove = `schtasks /Delete /TN agent-harness-<id> /F`.
  - All idempotent. Guard each branch behind `detect_os()`.
- [ ] Wire `--apply` / `--remove` flags into `main`.
- [ ] **Verification (manual, per OS):** run `--dry-run`, then `--apply`, confirm the entry appears in the native scheduler, run the job once on-demand, then `--remove`. **Cannot be auto-tested from Windows for the *nix backends — mark as a colleague validation step.**
- [ ] **Commit** `feat(sched): apply/remove backends (needs per-OS validation)`

---

## Self-Review
- **Spec §5 coverage:** registry → T1; generators (cron/launchd/schtasks) → T2-3; OS detect + install + dry-run → T4; native apply/remove → T5. Repo-relative invocation → `repo_root()` + relative args (T1).
- **Placeholders:** none — code is concrete.
- **Type consistency:** `Job(id,args,cadence,time,dow)`, `to_cron_line/to_launchd_plist/to_schtasks_cmd(job,python,repo)`, `detect_os/plan/apply/remove` consistent across tasks.
- **Honest limit:** T5's *nix apply/remove can't be CI-tested from the author's Windows box — flagged for colleague/real-machine validation, not hidden.
