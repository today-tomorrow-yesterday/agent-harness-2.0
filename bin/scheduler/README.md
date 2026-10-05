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

Edit `REGISTRY` in `jobs.py`, then re-run `--apply`:

```python
Job("my-job", ["bin/my_job.py"], "daily", "08:00", safe_rerun=True)
Job("my-weekly", ["bin/my_weekly.py"], "weekly", "09:00", dow="SUN")
```

Cadence is `"daily"` or `"weekly"` (+ `dow` MON..SUN). Set `safe_rerun=True` only for
cheap, idempotent jobs (no `claude -p`, no external writes) — `bin/self_loop.py` may
re-run those automatically when they fail.

Have the job record what it actually did, so the health loop can tell "exited 0" from
"did its work":

```python
from harness_common import record_outcome
record_outcome("my-job", status="ok", produced=12)        # Python
```
```bash
python bin/record_outcome.py my-job --status ok --produced 12   # anything else
```

The job name must match the `Job` id. On Linux, cron keeps no run history, so this
outcome is the ONLY recency evidence the health loop has for the job.

## Reading back what is installed

- **`introspect.py`** — reads what the OS scheduler really has for this harness
  (crontab lines tagged `# agent-harness:<id>`, `agent-harness.<id>` launchd plists,
  `agent-harness-<id>` Windows tasks). An unreadable scheduler is reported as unknown,
  never as "nothing installed".
- **`python bin/verify_scheduled_tasks.py`** — registry vs installed: declared-not-
  installed, installed-not-declared, schedule mismatch, disabled. Exit 0 match, 1 drift,
  2 unknown / nothing installed yet.

`bin/self_loop.py`, `bin/conformance_check.py` and `bin/harness_metrics.py` use the same
module. See `docs/health.md` for the whole health chain.

## Status / caveats

- `REGISTRY` ships with generic, cross-platform jobs wired, but **nothing is installed**
  until you run `--apply`. Jobs that spend your subscription, write unattended, or delete
  files are listed commented-out in `jobs.py` — each is opt-in, with the reason given.
- The Linux/macOS `apply`/`remove` backends are implemented but need validation
  on a real machine (they were authored on Windows). `--dry-run` is safe anywhere.
