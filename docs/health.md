# Health checks and self-maintenance

An unattended system fails quietly. A job's login dies and it keeps exiting 0. A
scheduled task is deleted and nothing says so. A hook points at a script that moved. A
red test sits unread for a week. The programs below exist so this install can tell when
it is broken, fix the mechanical cases itself, and tell you about the rest exactly once.

Everything here runs on any OS (Windows, macOS, Linux), needs no API key, and is safe on
a fresh clone: a check that has nothing to read says **not configured** or **unknown**
and why. It never reports a pass it did not measure.

## The health chain at a glance

| Layer | Question | Program | Scheduled by default |
|---|---|---|---|
| Detect (code) | Is the code right? | `bin/self_test.py` | daily 05:30 |
| Detect (wiring) | Is everything still wired? | `bin/conformance_check.py` | daily 06:00 |
| Heal | Is the fleet alive? Re-run what failed | `bin/self_loop.py` | daily 06:30 |
| Watch the healer | Is the self-loop itself alive? | `bin/fleet_status.py` | daily 07:15 |
| Fix code | Repair a red self-test | `bin/test_medic.py` | opt-in |
| Drift | Did model/CLI behaviour change? | `bin/golden_run.py` | opt-in |

Install the scheduled ones with `python bin/scheduler/install.py --apply` (see
`bin/scheduler/README.md`). Nothing is installed until you do.

## Shared plumbing (`bin/harness_common.py`)

Every program uses the same helpers, so one path can't quietly be weaker than another.

- **Outcomes** — `record_outcome(job, status, produced, detail)` writes
  `forge/outcomes/<job>.json`: what the job actually did, not just that it exited 0.
  Status is one of `ok | empty | transient | auth_failed | rate_limited | error`
  (`empty` = ran fine, nothing to do). `status=ok` with `produced=0` raises an alert —
  a job that did nothing must say so. Non-Python jobs use
  `python bin/record_outcome.py <job> --status ok --produced 12`.
  `read_outcome(job)` and `require_fresh(producer, max_age_h)` let a job refuse to run
  on stale input instead of reporting a clean run over nothing.
- **State-gated alerts** — `alert(job, message)` always appends to `forge/alerts.log`,
  but posts to Slack only when a condition goes from OK to BROKEN, and again if it is
  still broken at 7, 14, 28 ... days. While it stays broken it is listed by
  `open_issues()` instead of repeating. Volatile numbers (ages, exit codes) don't create
  new conditions; a change of failure class (auth vs rate limit) does. Slack is optional:
  with no webhook configured, the log and ledger still work.
- **Kill-switch** — every program honours `forge/STOP` (`python bin/runner/stop.py on`).
- **Dry-run** — `set_dry_run(True)` makes every outcome write and alert in the process
  inert, so looking at a job never overwrites its last real health record.
- **Locks** — `single_instance(job)` stops two runs racing; a lock left by a killed
  process is reclaimed.
- **Secrets** — `scrub_secrets(text)` is the canonical "what a secret looks like" list;
  alerts and outcome details pass through it before they are written or sent.
- **Headless model calls** — `claude_json(prompt, schema)` runs one `claude -p` call on
  your subscription. `clean_env()` strips any metered API key from the child environment
  so a background job can never move onto per-token billing.

## The programs

### `bin/self_test.py` — is the code right?
Runs the test suite, the brain health check, a gbrain probe, and the scheduler-vs-registry
check; writes `self-test-report.md`. Components not set up are SKIPPED with the reason. A
red verdict raises one alert; a green one clears it.
`python bin/self_test.py --print`

### `bin/self_loop.py` — is the fleet alive?
Reads what the OS scheduler actually has installed plus every job's outcome, and
classifies each declared job: `MISSING`, `UNDECLARED`, `DISABLED`, `NEVER_FIRED`, `STALE`,
`FAILED`, `RAN-BUT-FAILED` (exited 0 but its outcome says it did not do its work),
`STALE-OUTCOME` (keeps firing, but its outcome stopped updating). Jobs marked
`safe_rerun=True` are re-run on failure — at most twice per 24h, then re-runs pause and it
escalates. It does not spend a re-run when the job's own slot is under 3h away, or when its
last run hit a usage limit that has not reset yet. Recoveries get a green message only with
evidence (a fresh `ok`/`empty` outcome). Writes `forge/self-loop-latest.md` and a heartbeat.
`python bin/self_loop.py --dry-run`

What each OS can report differs: Windows Task Scheduler keeps last-run time and result;
launchd keeps the last exit status; cron keeps neither. On Linux, a job's recency
therefore comes only from its outcome file. A job with no evidence at all is reported
**recency unknown**. It is never assumed healthy, and never paged as stale.

### `bin/conformance_check.py` — is everything still wired?
Eleven structural questions, each answered with a number and a threshold:
registry scripts exist and compile · installed jobs match the registry · memory index
within its read budget · every repo skill is invokable · installed skill copies match the
repo · every wired hook points at a script that exists · brain DB reachable · secret files
readable only by their owner (POSIX mode bits; `icacls` on Windows) · brain-backup growth
bounded · untracked-file exposure · alert ledger readable. Each answer is PASS, FAIL, WARN,
SKIP (not configured) or BLIND (could not measure). It exits 0 when it ran, because a
checker that reports problems is working. Each FAIL is its own alert.
`python bin/conformance_check.py --dry-run`

### `bin/fleet_status.py` — one read-only view
Kill-switch, last-24h runs, every job's last outcome, open issues, locks, recent alerts,
the self-test verdict. It is also the **dead-man's switch**: the self-loop can't report its
own death, so a stale heartbeat raises an alert about the self-loop that only the
self-loop's own recovery can clear.
`python bin/fleet_status.py --dry-run`

### `bin/verify_scheduled_tasks.py` — registry vs installed
Lists declared-not-installed, installed-not-declared, schedule mismatches and disabled
jobs. Exit 0 = match, 1 = drift, 2 = unknown or nothing installed.

### `bin/harness_metrics.py` — the ruler
Measured counts, each with the list it counted: jobs declared and installed, scripts,
hooks, brain size, skills (repo vs profile), rules, credential key NAMES (never values),
job outcomes. A store it can't read shows `available: false` and a reason, never 0.
`python bin/harness_metrics.py --json --stable` is diffable.

### `bin/test_medic.py` — repair a red self-test (opt-in)
One headless `claude -p` repair attempt per run, under a contract: no git changes, never
weaken a test, escalate anything that needs a person. Success is decided by re-running the
self-test, never by the model's claim. Read the trust-model section in the README before
enabling it. `python bin/test_medic.py --dry-run` diagnoses only.

### `bin/golden_run.py` — drift canary (opt-in)
Runs the cases in `forge/golden/<family>.jsonl` in ONE `claude -p` call. It checks each
answer with an exact rule (no model judges another model) and appends the pass rate to
`forge/golden-history.jsonl`. A drop of more than 20 points from the recent best pages. A
rate limit or timeout is kept out of the history. A refusal of the whole batch counts as
0/N. `python bin/golden_run.py --dry-run` prints the prompt.

### `bin/auth_canary.py` — does the login work unattended? (opt-in)
Run it once from the scheduler. It records whether the session is interactive (where the
OS can tell) and whether `claude -p` authenticates there → `forge/auth-canary.json`.
`--dry-run` probes the session without calling the model.

### `bin/skill_canary.py` — gate a skill edit before it goes live
Snapshot the installed copy → check the repo copy is invokable and its helper scripts
compile → log to `forge/evolution.jsonl` → promote only on pass, with `--rollback`.
`--check-all` checks every repo skill and writes nothing. See `skills/skill-canary/`.

### `bin/rule_contradictions.py` — standing rules that disagree
Groups `memory/**/*.md` by the paths they give instructions about, then asks the model
(one call per pair, cached for a week, capped by `--max`) whether each pair can both be
followed. `--dry-run` lists candidate pairs and calls nothing.

### `bin/sibling_sweep.py` — the same bug, elsewhere
When a bug is fixed in one file, the same bug is often still in a sibling file. This sweep
checks `bin/` for patterns that have shipped more than once: a dry-run that still writes
health records, `claude -p` without `clean_env`, start-anchored "allowlists", ages computed
from mtime, and Bash granted with no untrusted-input rule. Silence a deliberate case with
`# sibling-sweep: ok <rule-name> — <reason>`. `--strict` exits 1 on findings.

### `bin/tmp_purge.py` — keep a scratch dir disposable (opt-in)
Deletes files older than `--days` (default 14) from `<repo>/tmp` (or `$HARNESS_TMP_DIR`).
It refuses a filesystem root, your home directory, the repo root, or any folder with a
`.git`. `--dry-run` lists what would go.

### `bin/release_gate.py` — before a change ships
Self-test + skill canary `--check-all` + conformance (no FAIL, no BLIND). All must pass.
Appends a record to `forge/eval_runs.jsonl`. `--dry-run` lists the checks.

## Where state lives

All under the repo, per machine, not committed:
`forge/outcomes/`, `forge/alerts.log`, `forge/alert-state.json`, `forge/locks/`,
`forge/self-loop-latest.md`, `forge/self-loop-heartbeat`, `forge/golden-history.jsonl`,
`forge/rule-contradictions.md`, `forge/rule-contradictions-cache.json`,
`forge/skill-versions/`, `forge/auth-canary.json`, `forge/eval_runs.jsonl`,
`self-test-report.md`, `logs/`.
