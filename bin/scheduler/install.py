"""Install/remove the harness's scheduled jobs natively per-OS.

`detect_os` + `plan` are pure (testable anywhere). `apply`/`remove` perform the
OS-specific side effects (crontab / launchd / schtasks) and are guarded per-OS.

CLI:
    python bin/scheduler/install.py --dry-run    # show what would be installed
    python bin/scheduler/install.py --apply      # install for this OS
    python bin/scheduler/install.py --remove     # uninstall
"""
from __future__ import annotations

import argparse
import os
import platform
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import backends as _be  # noqa: E402
import jobs as _jobs  # noqa: E402


def detect_os(name: str | None = None) -> str:
    s = (name or platform.system()).lower()
    return {"darwin": "macos", "linux": "linux", "windows": "windows"}.get(s, s)


def plan(os_name: str, python: str, repo: str, registry=None) -> list[str]:
    """Return the artifact text per job for the given OS (no side effects)."""
    registry = _jobs.REGISTRY if registry is None else registry
    out: list[str] = []
    for j in registry:
        if os_name == "linux":
            out.append(_be.to_cron_line(j, python, repo))
        elif os_name == "macos":
            out.append(_be.to_launchd_plist(j, python, repo))
        elif os_name == "windows":
            out.append(" ".join(_be.to_schtasks_cmd(j, python, repo)))
    return out


# --- side-effectful backends (guarded; needs per-OS validation) ---------------

def _linux_apply(python: str, repo: str) -> None:
    existing = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
    kept = [ln for ln in existing.splitlines() if "# agent-harness:" not in ln]
    new = [_be.to_cron_line(j, python, repo) for j in _jobs.REGISTRY]
    payload = "\n".join([*kept, *new]).strip() + "\n"
    subprocess.run(["crontab", "-"], input=payload, text=True, check=True)


def _linux_remove() -> None:
    existing = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
    kept = [ln for ln in existing.splitlines() if "# agent-harness:" not in ln]
    subprocess.run(["crontab", "-"], input="\n".join(kept).strip() + "\n", text=True, check=True)


def _macos_apply(python: str, repo: str) -> None:
    la = Path.home() / "Library" / "LaunchAgents"
    la.mkdir(parents=True, exist_ok=True)
    for j in _jobs.REGISTRY:
        f = la / f"agent-harness.{j.id}.plist"
        f.write_text(_be.to_launchd_plist(j, python, repo), encoding="utf-8")
        subprocess.run(["launchctl", "unload", str(f)], capture_output=True)
        subprocess.run(["launchctl", "load", "-w", str(f)], check=True)


def _macos_remove() -> None:
    la = Path.home() / "Library" / "LaunchAgents"
    for j in _jobs.REGISTRY:
        f = la / f"agent-harness.{j.id}.plist"
        if f.exists():
            subprocess.run(["launchctl", "unload", str(f)], capture_output=True)
            f.unlink()


def _windows_apply(python: str, repo: str) -> None:
    for j in _jobs.REGISTRY:
        subprocess.run(_be.to_schtasks_cmd(j, python, repo), check=True)


def _windows_remove() -> None:
    for j in _jobs.REGISTRY:
        subprocess.run(["schtasks", "/Delete", "/TN", f"agent-harness-{j.id}", "/F"],
                       capture_output=True)


def apply(os_name: str, python: str, repo: str) -> None:
    {"linux": lambda: _linux_apply(python, repo),
     "macos": lambda: _macos_apply(python, repo),
     "windows": lambda: _windows_apply(python, repo)}[os_name]()


def remove(os_name: str) -> None:
    {"linux": _linux_remove, "macos": _macos_remove, "windows": _windows_remove}[os_name]()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Install/remove harness scheduled jobs.")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    g.add_argument("--remove", action="store_true")
    ns = ap.parse_args(argv)

    os_name = detect_os()
    python = sys.executable
    repo = str(_jobs.repo_root())

    if ns.remove:
        remove(os_name)
        print(f"Removed harness jobs ({os_name}).")
        return 0
    if ns.apply:
        apply(os_name, python, repo)
        print(f"Installed harness jobs ({os_name}).")
        return 0
    # default: dry-run
    print(f"# OS={os_name}  python={python}  repo={repo}\n")
    print("\n---\n".join(plan(os_name, python, repo)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
