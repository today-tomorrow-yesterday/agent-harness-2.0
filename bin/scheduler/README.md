# Cross-platform scheduler

Register the harness's background jobs on a schedule on **Windows, macOS, or
Linux** from one declarative registry. The job *logic* is plain Python; only the
*registration* is OS-specific.

## How it works

- **`jobs.py`** — a `Job` dataclass + the `REGISTRY` list (your jobs). Each job's
  `args` are **repo-relative** so they work in any clone on any machine.
- **`backends.py`** — pure generators that turn a `Job` into the native artifact:
  `cron` line (Linux), `launchd` plist (macOS), `schtasks` command (Windows).
- **`install.py`** — detects the OS, generates entries, and installs/removes them.

## Usage

```bash
python bin/scheduler/install.py --dry-run   # show what would be installed (any OS)
python bin/scheduler/install.py --apply     # install for this OS
python bin/scheduler/install.py --remove    # uninstall
```

`--apply` writes to your user crontab (Linux), `~/Library/LaunchAgents` +
`launchctl` (macOS), or Task Scheduler via `schtasks` (Windows). Idempotent —
re-running replaces the harness's own entries (tagged `agent-harness`).

## Adding a job

Edit `REGISTRY` in `jobs.py`:

```python
REGISTRY = [
    Job("my-report", ["bin/my-report.py"], "daily",  "08:00"),
    Job("weekly",    ["bin/weekly.py"],    "weekly", "09:00", dow="SUN"),
]
```

Cadence is `"daily"` or `"weekly"` (+ `dow` MON..SUN). Re-run `--apply`.

## Status / caveats

- `REGISTRY` ships **empty** so a fresh clone never schedules a broken job.
- The bundled `bin/weekly-planner.py` and `bin/daily-brief.py` are currently
  **author/CLONE-specific** (hardcoded paths + farmer-pipeline logic). Genericize
  them (make paths repo-relative, drop CLONE/farmer inputs) **before** adding them
  to `REGISTRY`.
- The Linux/macOS `apply`/`remove` backends are implemented but need validation
  on a real machine (they were authored on Windows). `--dry-run` is safe anywhere.
