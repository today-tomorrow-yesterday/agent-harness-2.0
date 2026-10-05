#!/usr/bin/env python3
"""conformance_check.py — structural health, as opposed to execution health.

self_loop.py asks "did the jobs run?" and heals what didn't. Nothing else asks "is
everything still WIRED?" — so a job can be added and never installed, a hook can point at
a script that moved, an index can grow past the point where anyone reads it, a secret can
sit world-readable. Each of those is created by a CORRECT action, produces no error, and
leaves the system less correct. That is the drift mechanism, and this is the loop for it.

Every assertion answers a question with a NUMBER and a threshold, not a vibe, and each can
be broken deliberately to prove it fires — the only way to know a check checks anything.

STATUS of each assertion:
    PASS   measured, and within its threshold
    FAIL   measured, and a structural invariant is broken
    WARN   measured, drifted but not broken
    SKIP   not configured on this install (the reason says what is missing) — not a pass
    BLIND  tried to measure and could not — never a pass

Exit codes:
    0  the checker ran (assertion results travel in the report, the outcome sidecar and
       per-assertion alerts — a checker that reports problems is working, and a non-zero
       exit would make the healer treat it as broken)
    1  only with --exit-nonzero-on-fail, when an assertion FAILs (for humans and CI)
    2  an assertion was BLIND (the checker itself could not see)

    python bin/conformance_check.py            # human table
    python bin/conformance_check.py --json     # machine payload
    python bin/conformance_check.py --dry-run  # measure + print; record nothing, page nobody
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))
import harness_common as hc  # noqa: E402

JOB_ID = "conformance-check"
# Rough tokens-per-char for English markdown, deliberately conservative: better to flag an
# index as too big slightly early than to let it silently stop being read.
CHARS_PER_TOKEN = 3.6
INDEX_BUDGET_TOKENS = 6000
MAX_UNTRACKED = 50
BACKUP_BUDGET_GB = 2.0
BLANKET_PRINCIPALS = ("Everyone", "BUILTIN\\Users", "Authenticated Users")


@dataclass
class Result:
    id: str
    question: str
    status: str          # PASS | FAIL | WARN | SKIP | BLIND
    observed: str
    expected: str
    detail: str = ""


def _cap(items, n: int = 6) -> str:
    """A detail list that can never silently understate its own count."""
    items = list(items)
    head = ", ".join(str(x) for x in items[:n])
    return f"[{head}, …+{len(items) - n} more]" if len(items) > n else f"[{head}]"


# ---------------------------------------------------------------- assertions
def c1_registry_integrity() -> Result:
    """A registry entry pointing at a moved or broken script installs a job that fails
    every night without anyone having changed the job."""
    from scheduler import jobs as _jobs  # noqa: PLC0415
    q = "Does every declared job point at a script that exists and compiles?"
    bad = []
    ids = [j.id for j in _jobs.REGISTRY]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    for j in _jobs.REGISTRY:
        script = ROOT / j.args[0]
        if not script.exists():
            bad.append(f"{j.id}: missing {j.args[0]}")
        elif script.suffix == ".py":
            try:   # builtin compile(): checks syntax without writing any bytecode file
                compile(script.read_bytes(), str(script), "exec")
            except (SyntaxError, ValueError, UnicodeDecodeError) as e:
                bad.append(f"{j.id}: does not compile ({type(e).__name__}: {str(e)[:60]})")
    bad += [f"duplicate id {d}" for d in dupes]
    return Result("C1", q, "PASS" if not bad else "FAIL",
                  f"{len(bad)} problem(s) in {len(ids)} job(s)", "0", _cap(bad) if bad else "")


def c2_scheduler_matches_registry(query=None) -> Result:
    """Declared-but-not-installed means a capability is dark; installed-but-not-declared
    means a job runs that nothing audits."""
    from scheduler import introspect as _intro  # noqa: PLC0415
    from scheduler import jobs as _jobs  # noqa: PLC0415
    q = "Do the installed scheduled jobs match the registry?"
    installed, why = (query or _intro.query)()
    if installed is None:
        return Result("C2", q, "BLIND", "scheduler unreadable", "match", why)
    if not installed:
        return Result("C2", q, "SKIP", "no harness jobs installed", "match",
                      f"{why} — run bin/scheduler/install.py --apply")
    drift = _intro.reconcile(_jobs.REGISTRY, installed)
    fails = [d for d in drift if d[0] == "FAIL"]
    status = "FAIL" if fails else ("WARN" if drift else "PASS")
    return Result("C2", q, status, f"{len(drift)} drift item(s)", "0",
                  _cap(f"{k} {i}" for _, k, i, _ in drift) if drift else "")


def c3_index_within_budget() -> Result:
    """An index too large to load stops being loaded, silently."""
    q = "Is the memory index within its read budget?"
    idx = ROOT / "memory" / "MEMORY.md"
    if not idx.exists():
        return Result("C3", q, "SKIP", "no memory/MEMORY.md", f"<={INDEX_BUDGET_TOKENS} tokens")
    approx = int(len(idx.read_text(encoding="utf-8")) / CHARS_PER_TOKEN)
    return Result("C3", q, "PASS" if approx <= INDEX_BUDGET_TOKENS else "FAIL",
                  f"~{approx:,} tokens", f"<={INDEX_BUDGET_TOKENS:,}",
                  "an index over budget is skipped, not failed — silence is the symptom")


def c4_skills_conform() -> Result:
    """A malformed skill never loads and never errors (bin/skill_policy.py is the one
    definition of 'invokable')."""
    import skill_policy  # noqa: PLC0415
    q = "Is every repo skill an invokable SKILL.md?"
    roots = [r for r in skill_policy.owned_skill_roots() if r.is_dir()]
    if not roots:
        return Result("C4", q, "SKIP", "no skills root", "0 problems")
    found = skill_policy.audit_all()
    return Result("C4", q, "PASS" if not found else "FAIL", f"{len(found)} problem(s)",
                  "0", _cap(f"{Path(p).parent.name}: {why[:60]}" for p, why in found)
                  if found else "")


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def c5_installed_skills_current() -> Result:
    """A skill edited in the repo but never re-installed means the profile runs an old
    copy — two answers to 'what does this skill do'."""
    from harness_metrics import claude_settings_path  # noqa: PLC0415
    q = "Are installed copies of repo skills identical to the repo?"
    prof = claude_settings_path().parent / "skills"
    repo = ROOT / "skills"
    if not prof.is_dir() or not repo.is_dir():
        return Result("C5", q, "SKIP", "no profile skills dir", "0 stale",
                      f"looked for {prof.name}/ in the Claude profile")
    stale, checked = [], 0
    for d in sorted(repo.iterdir()):
        src, dst = d / "SKILL.md", prof / d.name / "SKILL.md"
        if src.is_file() and dst.is_file():
            checked += 1
            if _sha(src) != _sha(dst):
                stale.append(d.name)
    if not checked:
        return Result("C5", q, "SKIP", "no repo skill is installed in the profile", "0 stale")
    return Result("C5", q, "PASS" if not stale else "WARN",
                  f"{len(stale)} of {checked} installed copies differ", "0",
                  (f"stale: {_cap(stale)} — re-copy, or gate it with bin/skill_canary.py "
                   f"--promote <skill>") if stale else "")


def _hook_commands(settings: dict) -> list[str]:
    cmds = []
    for groups in (settings.get("hooks") or {}).values():
        for g in groups or []:
            for h in (g or {}).get("hooks", []) or []:
                if isinstance(h, dict) and h.get("command"):
                    cmds.append(str(h["command"]))
    return cmds


def _script_paths(cmd: str) -> list[Path]:
    import shlex  # noqa: PLC0415
    try:
        toks = shlex.split(cmd, posix=True)
    except ValueError:
        toks = cmd.split()
    out = []
    for t in toks:
        t = t.strip("\"'")
        if t.endswith((".py", ".sh", ".ps1")) and ("/" in t or "\\" in t):
            p = Path(os.path.expandvars(os.path.expanduser(t)))
            if p.is_absolute():
                out.append(p)
    return out


def c6_hooks_point_at_scripts() -> Result:
    """A hook whose script moved fails on EVERY tool call, usually silently."""
    from harness_metrics import claude_settings_path, read_settings  # noqa: PLC0415
    q = "Does every wired hook point at a script that exists?"
    st = read_settings()
    if st is None:
        return Result("C6", q, "SKIP", "no readable settings.json", "0 dangling",
                      str(claude_settings_path().name))
    cmds = _hook_commands(st)
    paths = [p for c in cmds for p in _script_paths(c)]
    missing = sorted({p.name for p in paths if not p.exists()})
    return Result("C6", q, "PASS" if not missing else "FAIL",
                  f"{len(missing)} dangling of {len(paths)} script path(s) in {len(cmds)} hook(s)",
                  "0", _cap(missing) if missing else "")


def c7_brain_reachable() -> Result:
    """An unmeasurable store must never render as an empty one."""
    from harness_metrics import claude_brain  # noqa: PLC0415
    q = "Is the brain DB reachable and its schema readable?"
    cb = claude_brain()
    if not cb.get("available"):
        reason = cb.get("reason", "")
        if "not set up" in reason:
            return Result("C7", q, "SKIP", "brain not set up", "reachable", reason)
        return Result("C7", q, "FAIL", "unreachable", "reachable", reason)
    if not cb.get("schema_ok"):
        return Result("C7", q, "WARN", "schema moved (a count returned NULL)", "readable")
    return Result("C7", q, "PASS", f"{cb.get('messages')} messages", "reachable")


def _secret_files() -> list[Path]:
    d = ROOT / "bin" / "secrets"
    if not d.is_dir():
        return []
    return [p for p in d.iterdir() if p.is_file()
            and not p.name.lower().startswith("readme") and not p.name.endswith(".template")]


def _broad_access(p: Path, runner=subprocess.run) -> tuple[bool | None, str]:
    """(True if readable by principals beyond the owner, detail). None = could not tell.
    POSIX: group/other permission bits. Windows: `icacls` ACEs for blanket principals."""
    if os.name != "nt":
        mode = p.stat().st_mode
        return bool(mode & (stat.S_IRWXG | stat.S_IRWXO)), oct(mode & 0o777)
    try:
        r = runner(["icacls", str(p)], capture_output=True, text=True, timeout=30)
    except Exception as e:  # noqa: BLE001
        return None, repr(e)[:80]
    if r.returncode != 0 or not (r.stdout or "").strip():
        return None, f"icacls exited {r.returncode}"
    hits = sorted({b for b in BLANKET_PRINCIPALS if b.lower() in r.stdout.lower()})
    return bool(hits), ", ".join(hits)


def c8_secrets_restricted(runner=subprocess.run) -> Result:
    """Inherited permissions are what a file gets when nobody looked. This cannot repair
    them (that needs the owner's decision); it refuses to let them stay invisible."""
    q = "Are the secret files readable only by their owner?"
    files = _secret_files()
    if not files:
        return Result("C8", q, "SKIP", "no secret files present", "owner-only",
                      "bin/secrets/ holds only templates")
    broad, blind = [], []
    for f in files:
        verdict, detail = _broad_access(f, runner)
        if verdict is None:
            blind.append(f"{f.name}: {detail}")
        elif verdict:
            broad.append(f"{f.name} ({detail})")
    if blind and not broad:
        return Result("C8", q, "BLIND", f"{len(blind)} file(s) unmeasurable", "owner-only",
                      _cap(blind))
    fix = ("chmod 600 bin/secrets/<file>" if os.name != "nt" else
           "icacls bin\\secrets\\<file> /inheritance:r /grant:r %USERNAME%:F")
    return Result("C8", q, "PASS" if not broad else "FAIL",
                  f"{len(broad)} of {len(files)} readable beyond the owner", "0",
                  (f"{_cap(broad)} — fix: {fix}") if broad else "")


def c9_backup_growth_bounded() -> Result:
    """Stores that only grow eventually cost more than they return. Reported, never
    deleted — removing anyone's only copy of anything is not a check's job."""
    q = "Is brain-backup growth bounded?"
    from harness_metrics import brain_db_path  # noqa: PLC0415
    db, why = brain_db_path()
    if db is None:
        return Result("C9", q, "SKIP", "brain not set up", f"<{BACKUP_BUDGET_GB} GB", why)
    d = db.parent
    if not d.is_dir():
        return Result("C9", q, "SKIP", "brain directory absent", f"<{BACKUP_BUDGET_GB} GB")
    live = db.resolve() if db.exists() else None
    snaps = [p for p in d.rglob("*.db") if live is None or p.resolve() != live]
    gb = sum(p.stat().st_size for p in snaps) / 1_073_741_824
    return Result("C9", q, "PASS" if gb < BACKUP_BUDGET_GB else "FAIL",
                  f"{len(snaps)} snapshot(s), {gb:.2f} GB", f"<{BACKUP_BUDGET_GB:.2f} GB",
                  "delete the snapshots whose migration is proven — this check will not")


def c10_work_has_a_recovery_point(runner=subprocess.run) -> Result:
    """Untracked files are unrecoverable if deleted; tracked changes are not. So this
    thresholds on UNTRACKED only — counting every porcelain line once made a large,
    fully recoverable deletion a permanent FAIL while real exposure hid inside it."""
    q = "Does uncommitted work have a recovery point?"
    try:
        out = runner(["git", "-C", str(ROOT), "status", "--porcelain"],
                     capture_output=True, text=True, timeout=60)
    except Exception as e:  # noqa: BLE001
        return Result("C10", q, "BLIND", "git unavailable", f"<{MAX_UNTRACKED} untracked",
                      repr(e)[:120])
    if out.returncode != 0:
        if "not a git repository" in (out.stderr or ""):
            return Result("C10", q, "SKIP", "not a git checkout", f"<{MAX_UNTRACKED} untracked")
        return Result("C10", q, "BLIND", "git status failed", f"<{MAX_UNTRACKED} untracked",
                      (out.stderr or "")[:120])
    lines = [ln for ln in out.stdout.splitlines() if ln.strip()]
    untracked = [ln for ln in lines if ln.startswith("??")]
    return Result("C10", q, "PASS" if len(untracked) < MAX_UNTRACKED else "FAIL",
                  f"{len(untracked)} untracked (of {len(lines)} uncommitted paths)",
                  f"<{MAX_UNTRACKED} untracked",
                  "commit or ignore them — this only measures the exposure")


def c11_alert_ledger_readable() -> Result:
    """An unreadable ledger renders exactly like 'no open issues' unless someone asks."""
    q = "Is the alert ledger readable?"
    if not hc.ALERT_STATE.exists():
        return Result("C11", q, "SKIP", "no alert ledger yet", "readable",
                      "nothing has raised an alert on this install")
    issues = hc.open_issues()
    bad = [i for i in issues if i.get("job") == "alert-state"]
    if bad:
        return Result("C11", q, "FAIL", "unreadable", "readable", bad[0]["message"][:160])
    return Result("C11", q, "PASS", f"{len(issues)} open issue(s)", "readable",
                  _cap(f"{i['job']} ({i['age_d']:.1f}d)" for i in issues) if issues else "")


ASSERTIONS = [c1_registry_integrity, c2_scheduler_matches_registry, c3_index_within_budget,
              c4_skills_conform, c5_installed_skills_current, c6_hooks_point_at_scripts,
              c7_brain_reachable, c8_secrets_restricted, c9_backup_growth_bounded,
              c10_work_has_a_recovery_point, c11_alert_ledger_readable]


def run_all() -> list[Result]:
    results = []
    for fn in ASSERTIONS:
        try:
            results.append(fn())
        except Exception as exc:  # noqa: BLE001 — a crashed assertion is BLIND, never PASS
            results.append(Result(fn.__name__.split("_")[0].upper(), fn.__doc__ or fn.__name__,
                                  "BLIND", f"{type(exc).__name__}: {exc}"[:160], "-"))
    return results


def render(results: list[Result]) -> str:
    width = max(len(r.question) for r in results)
    L = [f"{'ID':<5}{'QUESTION':<{width + 2}}{'STATUS':<7}OBSERVED", "-" * (width + 50)]
    for r in results:
        L.append(f"{r.id:<5}{r.question:<{width + 2}}{r.status:<7}{r.observed}")
        if r.detail and r.status != "PASS":
            L.append(f"{'':<5}{'':<{width + 2}}{'':<7}{r.detail}")
    n = {s: sum(1 for r in results if r.status == s) for s in ("PASS", "FAIL", "WARN", "SKIP", "BLIND")}
    L.append(f"\n{n['PASS']} pass · {n['FAIL']} fail · {n['WARN']} warn · "
             f"{n['SKIP']} skipped (not configured) · {n['BLIND']} blind")
    return "\n".join(L)


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Structural health checks for this install.")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--dry-run", action="store_true",
                    help="measure and print; record no outcome, raise no alert")
    ap.add_argument("--exit-nonzero-on-fail", action="store_true",
                    help="exit 1 when an assertion FAILs (humans / CI, not the scheduler)")
    args = ap.parse_args(argv)
    hc.set_dry_run(args.dry_run, "conformance_check.py --dry-run")

    # Honor the kill-switch: STOP halts the fleet, jobs go stale, and a checker that pages
    # about staleness the operator deliberately caused trains them to ignore it.
    if not hc.guard_or_skip(JOB_ID):
        return 0

    results = run_all()
    print(json.dumps([asdict(r) for r in results], indent=2) if args.json else render(results))

    fails = [r for r in results if r.status == "FAIL"]
    blind = [r for r in results if r.status == "BLIND"]
    # Two claims, two channels: the OUTCOME says whether the CHECKER did its work (it did,
    # even when the news is bad); each failing assertion is its own state-gated alert, and
    # passing ones are resolved so a fixed assertion leaves the open-issues list.
    hc.record_outcome(JOB_ID, status="error" if blind else "ok",
                      produced=len(results) - len(blind),
                      detail=f"{len(results) - len(fails) - len(blind)} non-failing, "
                             f"{len(fails)} fail, {len(blind)} blind")
    if not hc.is_dry_run():
        hc.resolve_conditions([f"conformance:{r.id}" for r in results if r.status == "PASS"])
        for r in fails:
            hc.alert(f"conformance:{r.id}", f"{r.question} — {r.observed}")
    if blind:
        return 2
    if fails and args.exit_nonzero_on_fail:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
