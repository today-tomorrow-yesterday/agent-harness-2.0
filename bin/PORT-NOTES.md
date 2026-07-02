# Port Notes — runner / goal_loop / execution

Three safety/autonomy subsystems ported from the private `agent-os` repo into the
shareable `agent-harness` repo on 2026-06-20, genericized. **Files only — no git
operations were run.**

## What was ported

| Subsystem | Source | Dest | Files |
|---|---|---|---|
| **runner** (kill-switch + cost/action/time ceilings + audit DB + "while you were away" digest) | `Z:\agent-os\bin\runner\` | `bin/runner\` | `__init__.py`, `guard.py`, `events.py`, `run.py`, `stop.py`, `digest.py` |
| **goal_loop** (weekly goal assessment: parse goals → gather signals → verdicts → questions → recommend → render) | `Z:\agent-os\bin\goal_loop\` | `bin/goal_loop\` | `__init__.py`, `assess.py`, `goals_io.py`, `questions.py`, `recommend.py`, `report.py`, `research.py`, `signals.py` |
| **execution** (approval/risk/redaction/secrets policy layer; gated "hands") | `Z:\agent-os\bin\execution\` | `bin/execution\` | `__init__.py`, `approval.py`, `backends.py`, `cli.py`, `execute.py`, `policy.py`, `redaction.py`, `risk.py`, `secrets.py`, `store_login.py`, `actions/__init__.py`, `actions/read_web.py` |
| **tests** | `Z:\agent-os\bin\tests\` | `bin/tests\` | `test_execution.py`, `test_runner.py`, `test_goal_loop.py` |

`.pyc` / `__pycache__` artifacts were not copied.

## Audit verdict: confirmed generic

The 2026-06-20 drift audit was correct. None of the three subsystems import or
reference the proprietary CLONE / farmers / production-engine / business-skills
stack. The core safety machinery stands alone. Every import resolves against the
harness tree (`runner`, `execution`, `goal_loop` packages under `bin/`),
stdlib, or optional third-party (`keyring`, `pytest`). The only cross-subsystem
coupling is intentional and ported intact: `execution` depends on `runner`
(shares `forge/runner.db` + WAL + base schema) and `runner/digest.py` calls the
already-present `bin/notify_slack.py` (`post_slack`).

## Genericization changes of substance

Paths were **already** repo-relative in the source (`Path(__file__).resolve().parents[2]`
→ repo root; state under `forge/`), matching the harness convention in
`bin/scheduler/jobs.py`. No hardcoded absolute paths or drive letters existed to
fix. The remaining changes were identity/wording:

### runner
- `digest.py` — docstring + headings: "what needs Tre", "so Tre reviews", "keeps
  him ON the loop" → "what needs you" / "so you review" / "keeps you ON the loop".
  Pure-function behavior unchanged.

### goal_loop
- No identity/proprietary content found. Ported verbatim. (`research.py` shells out
  to a generic `claude -p` web-research call with `--fallback-model claude-sonnet-4-6`
  — a generic model id, kept as-is.)

### execution
- `__init__.py` — "hands of agent-os" → "hands of the harness"; removed the
  agent-os spec path (`docs/superpowers/specs/2026-06-19-...`).
- `approval.py` — docstring "Tre resolves it later" → "the operator resolves it";
  `resolve(..., by="tre")` default → `by="operator"`.
- `backends.py` — removed agent-os-specific framing ("the Claude Code WSL2 sandbox
  model … adopted via @anthropic-ai/sandbox-runtime"; the
  `docs/research/execution-layer-foundations.md` ref). Behavior (LocalBackend +
  ConfinedLocalBackend stub) unchanged.
- `cli.py` — `--by tre` defaults → `--by operator`; usage examples updated.
- `policy.py` — "an edit … = Tre's per-class sign-off" → "the operator's per-class
  sign-off". Default policy table unchanged.
- `secrets.py` — docstring removed "Sol" reference; keyring service namespace
  prefix changed from `agent-os/<service>` to a module constant
  `_SERVICE_NS = "agent-harness"` → `agent-harness/<service>` (see note below).
- `store_login.py` — was the most coupled file: hardcoded to **Sol's Gmail vault**
  ("Store a login in Sol's vault", fixed `gmail` service, prompts for a Gmail
  address, referenced `store-sol-login.cmd`). **Reworked into a generic credential
  storer** that prompts for (or takes argv) `service` + `account` + hidden
  password/token. Same safe getpass behavior, same `execution.secrets.set_secret`
  call. No `.cmd` launcher was ported (it was Sol-specific).

### tests
- `test_runner.py` — sample job name `"farmer"` → `"worker"` in the digest test
  (cosmetic; "farmer" is CLONE-flavored). Logic identical.
- `test_goal_loop.py` — sample goal data rewritten from CLONE-flavored
  ("Break into TikTok business", `yt-ops` repo) to neutral ("Launch the public
  beta", `app-core` repo). All assertions preserved/adjusted to the new strings.
- `test_execution.py` — `by="tre"` → `by="operator"` in the approval roundtrip.
  Test doubles + assertions otherwise verbatim.

## Could NOT cleanly port / flags

Nothing had to be dropped or stubbed for proprietary coupling. Two items to be
aware of:

1. **`store_login.py` was Sol/Gmail-specific** (the only identity-coupled file in
   the set). It was *genericized*, not dropped — the credential-storing behavior is
   generic; only the Sol/Gmail framing was. Original at
   `Z:\agent-os\bin\execution\store_login.py:1-39`. No `store-sol-login.cmd`
   launcher exists in the harness (intentionally not ported).

2. **keyring service-namespace change** (`secrets.py`): the source stored secrets
   under `agent-os/<service>`; the port uses `agent-harness/<service>`. This is a
   behavior change for *reading back already-stored* secrets, but in a fresh clone
   no secrets exist yet, and the namespace should not carry the source project's
   name. If you ever migrate a real vault, re-store under the new namespace.

## Imports — all resolve

Smoke-import from `bin/` passed for every ported module:
`runner.{events,guard,run,stop,digest}`,
`goal_loop.{assess,goals_io,questions,recommend,report,research,signals}`,
`execution.{approval,backends,cli,execute,policy,redaction,risk,secrets}`,
`execution.actions.read_web`. → `ALL IMPORTS OK`.

No ported module imports an agent-os module that wasn't ported. `keyring` is
present in this environment; `secrets.py` also degrades gracefully (imports even if
keyring is missing, raising `SecretsUnavailable` only on use).

## How to run the tests

From the harness root (`Z:\products\agent-harness`):

```
python -m pytest bin/tests/test_execution.py -q
# or all three ported suites:
python -m pytest bin/tests/test_execution.py bin/tests/test_runner.py bin/tests/test_goal_loop.py -q
```

`test_runner.py` and `test_goal_loop.py` load modules via `importlib` (unique
module names), so they need no `sys.path` setup. `test_execution.py` inserts `bin/`
on `sys.path` so `execution` and `runner` import as packages. All tests use a tmp
`runner.db` / tmp STOP file — **no real state is touched, no kill-switch is
triggered, no scheduled task is registered.**

## Validation results (this port)

- **Smoke imports:** PASS (`ALL IMPORTS OK`).
- **Ported tests:** `48 passed in ~1.3s`
  (`test_execution.py` 23, `test_runner.py` 14, `test_goal_loop.py` 11).
- **Full harness suite:** `114 passed, 1 failed`. The single failure —
  `test_scheduler.py::test_plan_empty_registry_is_safe` — is **pre-existing and
  unrelated to this port** (it asserts an empty scheduler REGISTRY, but
  `bin/scheduler/jobs.py` ships two registered jobs; neither file was touched here).

---

# Port 2 — generic safety improvements (2026-06-21)

A second sweep brought four **genuinely generic** improvements that landed in
`agent-os` after the first port. Everything else that differs between the repos is
the *intentional genericization* above (Tre/Sol → operator, `agent-os` → `agent-harness`)
and was deliberately left untouched — porting those back would re-introduce identity
into the public repo.

| Improvement | Files | Why generic |
|---|---|---|
| **Slack egress secret-scrub** + GH-markdown→mrkdwn conversion + webhook validation (`https://hooks.slack.com/` prefix check, `SLACK_WEBHOOK_FILE` env override) | `bin/notify_slack.py` | every Slack post now passes through `execution.redaction.scrub` before leaving the box — a token in a traceback or a raw `runner.db` dump can't ship off-box. No identity coupling. |
| **First gated mutation action** — `WriteWorkspace` (ships disabled in `DEFAULT_POLICY`, so it PARKS for approval; reversible `.bak`; self-protection deny-list refuses to write the policy/identity/execution code) | `bin/execution/actions/write_workspace.py` + `bin/tests/test_write_workspace.py` | `policy.py` already listed the `write_workspace` class; only the action file was missing. Deny-list targets the harness's own `memory/*.md` + `bin/{execution,runner}`. "Tre"→"operator" was the only wording change. |
| **STOP file now self-documenting** — JSON `{ts, reason}`, `reason()` accessor, `engage(reason)`, and a best-effort Slack alert on engage/clear so a stopped fleet can't go unnoticed | `bin/runner/stop.py` | backward-compatible (guards still only check existence). The alert was rewired from `agentos_common.alert` (not present here) to `notify_slack.post_slack`. |
| **git-call timeout** on the weekly signal gather | `bin/goal_loop/signals.py` | `timeout=30` so a locked repo can't hang the weekly brief. |

**Validation:** smoke imports OK; `scrub` confirmed redacting `xoxb`/`Bearer sk-`/JWT
shapes; full `bin/tests/` suite **121 passed** (was 114 + the 6 new write_workspace
tests, minus the pre-existing empty-registry scheduler test which now passes since the
registry ships jobs). No real state touched.

---

## Port batch — 2026-07-02 (the self-maintenance chain)

Ported from agent-os after its full-system hardening arc (262-test regression
fleet, autonomous inbox pipeline, three real production bugs found + fixed).
Everything below is generic — no operator identity, repo-relative paths only.

| Improvement | Files | Notes |
|---|---|---|
| **Self-Test** — the harness tests itself daily: full `bin/tests` + brain health + gbrain probe → `self-test-report.md`; fresh-clone-safe (unset-up components SKIP, not FAIL) | `bin/self_test.py` + `jobs.py` entry (05:30) | verdict surfaced by the digest |
| **Fleet-integrity guard** — REGISTRY-derived: every job's script exists + compiles; installed tasks not disabled + fired within cadence (Windows; skips gracefully pre-install / non-Windows) | `bin/tests/test_fleet_integrity.py` | derives from `jobs.py`, can't drift |
| **Hook stdin hardening** — `isinstance(dict)` guard + 61-case smoke suite: no hook may crash on malformed stdin (`null`/`42`/`[]`/garbage) | `claude-brain/hooks/user-prompt-submit.py`, `bin/tests/test_hooks_stdin.py` | crash class found live in agent-os twice |
| **FIXED SHIPPED BUG:** `claude-brain/lib/paths.py` had a SyntaxError (`C:\Users\<USERNAME>` in a non-raw docstring → truncated `\U` escape) — brain_health + anything importing lib.paths was broken in every clone. Introduced by the genericization pass un-escaping the original's `\` | `claude-brain/lib/paths.py` (raw docstrings) | found BY the ported self-test on its first run |
| **Test-Medic (opt-in)** — scheduled autonomous repair of a red self-test: repair contract + git-HEAD verification + deterministic re-verify; ships as a commented-out Job | `bin/test_medic.py`, README "trust model" section | the one component granting unattended write access — hence opt-in |
| **Self-Loop** — fleet liveness auditor + mechanical healer: MISSING/DISABLED/NEVER_FIRED/STALE/FAILED classification, safe_rerun heals (bounded + 24h cooldown), deduped Slack escalation | `bin/self_loop.py`, `Job.safe_rerun` field | recency-based — result codes alone are blind to a task that stopped firing |
| **Scheduler resilience** — post-create settings patch: `StartWhenAvailable` (missed-trigger catch-up) + `RestartCount 3 / 30m` (failed-launch retry) | `backends.to_schtasks_settings_patch` + `install._windows_apply` | learned from a weekly job that silently lost a week to a refused Sunday launch |
| **Digest self-test verdict line** — `**Self-test:** PASS/FAIL`, with a >26h STALE flag (a stopped report means the self-test JOB died) | `bin/runner/digest.py` (`selftest_line`) + tests | |
| **Path-integrity guard template** — the post-reorg stale-path regression test, with the hard-won tuning notes (skip generated narrative, word-boundary patterns, guard-doc self-trips) | `docs/path-integrity-guard.md` | caught 5 live stragglers + 1 agent-reintroduced ref in its first week |

**Validation:** full suite green after the batch (see commit); fresh-clone simulation
(config.yaml absent) → self-test VERDICT: PASS with brain/gbrain SKIPPED.
