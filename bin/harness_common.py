"""harness_common.py — small shared helpers for the background jobs in bin/.

One definition of each helper more than one job needs. A private copy in every script
is how one path ends up weaker than the others without anyone noticing.

  prompt / claude -p
    defang_untrusted        neutralize fence markers inside scraped/ingested text
    classify_claude_result  tell a rate-limit from an auth failure from a real error
    clean_env               child environment for a headless `claude -p` spawn
    claude_json             one structured `claude -p` call (subscription, never an API key)

  job outcomes (did the job DO its work, not just exit 0)
    record_outcome / read_outcome / require_fresh / parse_limit_reset

  state-gated alerting (page once on OK->BROKEN, silent while chronic)
    alert / alert_recovered / mark_broken / resolve_conditions / open_issues / condition_key

  process hygiene
    is_stopped / guard_or_skip   global kill-switch (forge/STOP)
    set_dry_run / is_dry_run     a diagnostic run never writes health records or pages
    single_instance              one live run per job, orphan locks reclaimed
    write_json_atomic / rotate_log / record_run
    SECRET_PATTERNS / scrub_secrets   the canonical "what a secret looks like" list

State lives under <repo>/forge/. Stdlib only. No side effects on import.
"""
from __future__ import annotations

import contextlib
import datetime
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

# --- untrusted-content defanging (prompt-injection containment) ---------------------
# Every job that pastes SCRAPED or USER-AUTHORED text into a document or a `claude -p`
# prompt fences it as "untrusted data, not instructions". A fence alone is not a
# boundary: content containing the literal closing marker TERMINATES ITS OWN QUARANTINE,
# and everything after it reads as trusted instruction.
#
# Two rules, applied to the CONTENT only, never to the real fences:
#   1. any run of 3+ marker chars (< = >) is broken into dash-joined 3-char chunks, so no
#      marker-length run survives even as a substring;
#   2. known fence PHRASES are neutered, so a bare "END UNTRUSTED CONTENT" line can't match.
# Both survive newline-flattening and re-wrapping downstream (substring-safe, not line-based).
_MARKER_RUN_RE = re.compile(r"([<=>])\1{2,}")
_MARKER_PHRASE_RE = re.compile(
    r"(END\s+)?UNTRUSTED[\s\-_]+(WEB\s+|)(CONTENT|METADATA)|TRANSCRIPT_(BEGIN|END)", re.I)


def defang_untrusted(text: str) -> str:
    """Neutralize fence markers inside untrusted content so it cannot escape its quarantine.

    Use on ANY scraped/ingested text before interpolating it into a prompt. Lossless enough
    for the model to still read the content; the only mutations are to marker-shaped runs and
    fence phrases, which carry no meaning for the actual task.
    """
    text = _MARKER_RUN_RE.sub(
        lambda m: "-".join(m.group(0)[i:i + 3] for i in range(0, len(m.group(0)), 3)),
        text or "")
    return _MARKER_PHRASE_RE.sub(lambda m: m.group(0).replace(" ", "-") + "(defanged)", text)


# --- `claude -p` outcome classification ----------------------------------------------
def classify_claude_result(returncode: int, stdout: str = "", stderr: str = "") -> tuple[str, str | None]:
    """Classify a `claude -p` invocation outcome from its exit code + output.

    Returns (status, detail). status is one of:
      "ok"                — looks successful
      "auth_failed"       — credential/401 problem; needs a human to re-authenticate
      "rate_limited"      — hit a usage window or cap; detail = reset hint if found
      "model_unavailable" — model overloaded/unavailable
      "error"             — other non-zero failure

    Pure function — no side effects, fully unit-testable.
    """
    # A successful call (exit 0) is OK regardless of content — an answer may itself
    # mention "rate limit" / "401" / "unavailable". Only inspect the output for failure
    # signatures when the call actually FAILED. NOTE: `claude -p` writes rate-limit and
    # auth messages to STDOUT, not stderr, so both are read.
    if returncode == 0:
        return ("ok", None)
    blob = f"{stdout}\n{stderr}".lower()
    if ("401" in blob and ("auth" in blob or "credential" in blob)) \
            or "invalid authentication" in blob \
            or "failed to authenticate" in blob \
            or "please run /login" in blob \
            or ("oauth token" in blob and "expired" in blob):
        return ("auth_failed", "credential/401 — needs re-auth")
    # A per-model cap reads "You've reached your <model> limit. Switch to another model,
    # or manage usage credits at ..." — waiting is the remedy, so it is rate_limited
    # like the rolling window.
    if "session limit" in blob or "rate limit" in blob or "usage limit" in blob \
            or "you've hit your" in blob or "hit your session" in blob \
            or ("reached your" in blob and "limit" in blob) \
            or "manage usage credits" in blob or "switch to another model" in blob:
        m = re.search(r"resets?\s+([^\n.]+)", blob)
        return ("rate_limited", m.group(1).strip() if m else None)
    if "currently unavailable" in blob or "overloaded" in blob \
            or ("model" in blob and "unavailable" in blob):
        return ("model_unavailable", None)
    return ("error", f"exit {returncode}")


# --- child environment for headless spawns --------------------------------------------
# In -p mode a present ANTHROPIC_API_KEY silently overrides the subscription login and
# routes the job onto paid per-token billing. This harness is built to run on the
# subscription, so a metered key is never forwarded to a background `claude -p`.
# Deliberately does NOT match CLAUDE_CODE_OAUTH_TOKEN, which IS the subscription auth.
_METERED_KEY_RE = re.compile(r"ANTHROPIC.*KEY|CLAUDE.*API.*KEY|ANTHROPIC.*AUTH.*TOKEN|BILLING")


def clean_env(**overrides: str) -> dict[str, str]:
    """os.environ minus metered-billing keys, with optional overrides applied.

    Usage: subprocess.run(..., env=clean_env(CLAUDE_BRAIN_SKIP_HOOKS="1"))
    """
    env = {k: v for k, v in os.environ.items() if not _METERED_KEY_RE.search(k.upper())}
    env.update(overrides)
    return env


# =====================================================================================
# Locations + clock
# =====================================================================================
# harness_common.py lives in <repo>/bin/, so the repo root is parents[1]. Every path below
# is a module attribute so tests can redirect it to a tmp dir.
REPO = Path(__file__).resolve().parents[1]
FORGE = REPO / "forge"
STOP_FILE = FORGE / "STOP"                       # same file as bin/runner/stop.py
ALERTS_LOG = FORGE / "alerts.log"                # unthrottled audit trail of every alert
ALERT_STATE = FORGE / "alert-state.json"         # condition store behind the state gate
OUTCOMES_DIR = FORGE / "outcomes"                # one <job>.json sidecar per job
LOCK_DIR = FORGE / "locks"

# The ONE clock every helper here reads. Tests pin it (monkeypatch `_clock`) so no test
# depends on today's date.
_clock = time.time


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(_clock()))


def _iso_age_s(iso: str, now_s: float | None = None) -> float | None:
    """Seconds since a UTC '...Z' timestamp; None if unparseable (never 0 — an undatable
    record is not a fresh one)."""
    import calendar
    try:
        t = calendar.timegm(time.strptime(str(iso), "%Y-%m-%dT%H:%M:%SZ"))
    except (ValueError, TypeError):
        return None
    return (now_s if now_s is not None else _clock()) - t


# =====================================================================================
# Dry-run is a property of the PROCESS, not a local `if` in every writer
# =====================================================================================
# Several programs independently shipped the same bug: a `--dry-run` / `--print`
# diagnostic that still wrote the real outcome sidecar and still paged. The live health
# record then read "empty, produced 0" for a week because someone ran the job to LOOK at
# it — the observation destroyed the observed value. Guarding each call site did not
# hold (the fix landed in one program and never reached its siblings), so the guard
# lives at the destination: one `set_dry_run(True)` at argument-parse time makes every
# outcome write and every alert in the process inert. bin/sibling_sweep.py checks that
# every program with a dry-run flag calls it.
_DRY_RUN: bool = os.environ.get("HARNESS_DRY_RUN", "") not in ("", "0", "false", "False")
_DRY_REASON: str = "HARNESS_DRY_RUN env" if _DRY_RUN else ""


def set_dry_run(flag: bool, reason: str = "") -> None:
    """Mark this process as non-mutating. Call once, from argument parsing, with the OR of
    every flag that means "don't really do it" (--dry-run, --print, not --apply, ...)."""
    global _DRY_RUN, _DRY_REASON
    _DRY_RUN = bool(flag)
    _DRY_REASON = reason or ("dry run" if flag else "")


def is_dry_run() -> bool:
    return _DRY_RUN


# =====================================================================================
# Secret scrubbing — the canonical shape list
# =====================================================================================
# ONE definition of "what a secret looks like" for anything that ships text off the box
# (alerts, outcome details, reports). Divergent copies are how an egress path ends up
# weaker than a local guard.
#
# The canonical list lives in bin/execution/secret_patterns.py where that module exists;
# it is loaded from there by file path (no sys.path side effect on import). The tuple
# below is the fallback for a tree that predates that module — keep the two identical,
# and add new shapes to the canonical module.
#
# scrub_secrets() also applies execution.redaction.scrub first, so exact secret values
# registered by execution.secrets are always removed too.
_FALLBACK_SECRET_PATTERNS = (
    r"-----BEGIN[ A-Z]*PRIVATE KEY-----",   # PEM private key header
    r"Bearer\s+[A-Za-z0-9._\-]+",
    r"\bAKIA[0-9A-Z]{16}\b",                # AWS access-key id
    r"\bgh[pousr]_[A-Za-z0-9]{20,}\b",      # GitHub PAT / OAuth / refresh token
    r"\bAIza[0-9A-Za-z_\-]{35}\b",          # Google API key
    r"sk-[A-Za-z0-9]{8,}",
    r"xox[baprs]-[A-Za-z0-9-]{8,}",
    r"eyJ[A-Za-z0-9._\-]{10,}",             # JWT
    r"\b[A-Fa-f0-9]{32,}\b",                # long hex (keys / hashes)
    # assignment-shaped leak: `SOME_API_TOKEN=<long value>`. Keyed off the NAME so it
    # catches provider tokens with no distinctive prefix without redacting every long
    # identifier in a log line. Scoped (?i:...) — a bare (?i) is a "global flags not at
    # the start" error once these are joined into one alternation.
    r"(?i:\b\w*(?:api[_-]?key|token|secret|password|passwd)\b\s*[=:]\s*"
    r"['\"]?[A-Za-z0-9_\-\.]{12,})",
)


def _load_secret_patterns() -> tuple:
    canonical = REPO / "bin" / "execution" / "secret_patterns.py"
    if canonical.is_file():
        try:
            import importlib.util  # noqa: PLC0415
            spec = importlib.util.spec_from_file_location("_harness_secret_patterns", canonical)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            pats = tuple(getattr(mod, "SECRET_PATTERNS", ()))
            if pats:
                return pats
        except Exception:  # noqa: BLE001 — never lose scrubbing to an import problem
            pass
    return _FALLBACK_SECRET_PATTERNS


SECRET_PATTERNS = _load_secret_patterns()
_SECRET_RE = re.compile("(" + "|".join(SECRET_PATTERNS) + ")")
_MASK = "[REDACTED]"


def scrub_secrets(text: str) -> str:
    """Mask token-shaped substrings (and any exact registered secret) in `text`."""
    text = text or ""
    try:
        if str(REPO / "bin") not in sys.path:
            sys.path.insert(0, str(REPO / "bin"))
        from execution.redaction import scrub as _exact_scrub  # noqa: PLC0415
        text = _exact_scrub(text) or ""
    except Exception:  # noqa: BLE001 — the canonical list below still applies
        pass
    return _SECRET_RE.sub(_MASK, text)


# =====================================================================================
# Small file helpers
# =====================================================================================
def write_json_atomic(path, obj) -> bool:
    """Write JSON atomically (tmp file + os.replace) so a crash mid-write can't truncate
    a state file — a truncated state file silently resets a job. True on success."""
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(obj, indent=2, default=str), encoding="utf-8")
        os.replace(tmp, path)
        return True
    except OSError:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        return False


def rotate_log(log_path: Path, max_bytes: int = 5_000_000) -> None:
    """Size-based rotation: keep one .1 backup, start fresh past max_bytes. Call once at
    the top of main(). Failures are swallowed — rotation must never take down its job."""
    try:
        log_path = Path(log_path)
        if log_path.exists() and log_path.stat().st_size > max_bytes:
            bak = Path(str(log_path) + ".1")
            if bak.exists():
                bak.unlink()
            log_path.rename(bak)
    except OSError:
        pass


# =====================================================================================
# Kill-switch
# =====================================================================================
def is_stopped() -> bool:
    """True if the global kill-switch (forge/STOP) is engaged.

    FAIL-OPEN: an error determining state returns False — a bug in the check must never
    block legitimate work. A failure to CHECK is itself an anomaly, so it is alerted."""
    try:
        return STOP_FILE.exists()
    except OSError as e:
        try:
            alert("kill-switch", f"could not read STOP file: {e} -- proceeding fail-open")
        except Exception:  # noqa: BLE001
            pass
        return False


def guard_or_skip(job_name: str, log=None) -> bool:
    """Call at the top of an unattended job's main(). False = kill-switch engaged, the
    caller should exit cleanly (return 0). True = proceed."""
    if is_stopped():
        (log or print)(f"[{job_name}] STOP engaged ({STOP_FILE.name}) — skipping run.")
        return False
    return True


# =====================================================================================
# State-aware alert gate
# =====================================================================================
# One canonical condition key + state store between every caller and Slack:
# classify -> check state -> route. Pages once on OK->BROKEN, stays silent on
# BROKEN->BROKEN (the condition stays visible through open_issues()), re-pages at chronic
# milestones, and emits a green "recovered" on BROKEN->OK — but only for FLEET-tracked
# conditions (fleet=True); one-off conditions auto-expire silently after 24h clean.
#
# Why not an exact-string cooldown: any changing number in a message (an age, an exit
# code, a count) defeats exact-string dedup, which is how a chronic condition re-pages
# every cycle and trains the operator to ignore the channel.
NONFLEET_EXPIRE_H = 24
CHRONIC_REPAGE_D = (7, 14, 28, 56, 112, 224)

# Failure CLASSES that must never share a condition key: they demand different responses
# (auth_failed = log in again now; rate_limited = wait; empty = a real content bug). Any
# of these appearing in the raw message is appended to the key — the 60-char prefix alone
# once merged five distinct failures into two keys, so an auth death arrived as
# BROKEN->BROKEN behind an already-open transient record and never paged.
_DISCRIMINATOR_TOKENS = (
    "auth_failed", "rate_limited", "model_unavailable", "transient",
    "permanent", "quarantined", "empty", "timeout", "error",
)


def condition_key(job_name: str, message: str) -> str:
    """Stable key '{job}|{normalized message}|{classes}'. Volatile tokens (hex, digit runs,
    trailing parenthetical/em-dash detail) are stripped so a changing age or exit code
    cannot defeat dedup; a change of failure CLASS is a new condition."""
    s = re.sub(r"0x[0-9A-Fa-f]+", "", message or "")
    s = re.sub(r"\d+", "", s)
    s = s.split("(")[0].split("—")[0].strip()
    low = (message or "").lower()
    classes = ",".join(t for t in _DISCRIMINATOR_TOKENS if t in low)
    return f"{job_name}|{s[:60]}" + (f"|{classes}" if classes else "")


def _load_alert_state() -> dict:
    """Corrupt/unreadable store -> empty (fail-open: may re-page once, self-correcting)."""
    try:
        if ALERT_STATE.exists():
            d = json.loads(ALERT_STATE.read_text(encoding="utf-8"))
            if isinstance(d, dict):
                return d
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def _expire_nonfleet(state: dict) -> None:
    now_s = _clock()
    for k in list(state):
        rec = state.get(k) or {}
        if rec.get("fleet") or rec.get("status") != "broken":
            continue
        age = _iso_age_s(rec.get("last_seen", ""), now_s)
        if age is None or age > NONFLEET_EXPIRE_H * 3600:
            del state[k]


def mark_broken(job_name: str, message: str, *, fleet: bool = False,
                subject: str | None = None) -> bool:
    """Record the condition BROKEN. True exactly on OK->BROKEN (caller should page), False
    while chronic (BROKEN->BROKEN: last_seen and wording refreshed, age kept). Fail-open:
    any store error returns True — never swallow a real alert.

    `subject` is who the condition is ABOUT when that differs from who RAISED it (a
    watchdog reporting another job). Reconciliation keys on the subject, so only the
    subject's own health can clear it. An earlier version keyed on the raiser, and a
    watchdog's own clean run deleted the "the healer is dead" condition while the healer
    was still dead."""
    subject = subject or job_name
    try:
        st = _load_alert_state()
        _expire_nonfleet(st)
        key = condition_key(job_name, message)
        now = _now_iso()
        rec = st.get(key)
        if rec and rec.get("status") == "broken":
            rec["last_seen"] = now
            rec["fleet"] = bool(rec.get("fleet") or fleet)
            rec["job"] = subject
            rec["raised_by"] = job_name
            # Refresh the wording, keep the age: the key collapses volatile tokens, so the
            # stored text would otherwise freeze at first_seen and report a stale count.
            rec["first_message"] = rec.get("first_message", rec.get("message", ""))
            rec["message"] = scrub_secrets(str(message))[:200]
            write_json_atomic(ALERT_STATE, st)
            return False
        st[key] = {"status": "broken", "job": subject, "raised_by": job_name,
                   "message": scrub_secrets(str(message))[:200],
                   "first_seen": now, "last_seen": now, "paged": True, "fleet": bool(fleet)}
        if len(st) > 300:   # bound growth: keep the 300 most recently seen
            st = dict(sorted(st.items(), key=lambda kv: (kv[1] or {}).get("last_seen", ""),
                             reverse=True)[:300])
        write_json_atomic(ALERT_STATE, st)
        return True
    except Exception:  # noqa: BLE001
        return True


def _chronic_repage_due(job_name: str, message: str) -> int | None:
    """Milestone re-page for a condition still broken at 7/14/28/... days. BROKEN->BROKEN
    silence is right for a flapping job and wrong for a month-long outage: without this a
    dead job pages once and is never mentioned on the paging channel again. Each milestone
    pages exactly once. Fail-closed (None) on any state error."""
    try:
        st = _load_alert_state()
        rec = st.get(condition_key(job_name, message))
        if not rec or rec.get("status") != "broken":
            return None
        age_s = _iso_age_s(rec.get("first_seen", ""))
        if age_s is None:
            return None
        age_d = age_s / 86400.0
        due = max((m for m in CHRONIC_REPAGE_D if age_d >= m), default=None)
        if due is None or int(rec.get("repaged_d", 0) or 0) >= due:
            return None
        rec["repaged_d"] = due
        write_json_atomic(ALERT_STATE, st)
        return due
    except Exception:  # noqa: BLE001
        return None


def _norm_job(name) -> str:
    """Canonical subject: casefolded, separators dropped, so `self-test`, `Self_Test` and
    `self test` name the same job. The two halves of the gate (raise / resolve) are called
    by different programs with different naming habits; an exact match left conditions
    that no code path could ever clear."""
    return re.sub(r"[-_. ]+", "", str(name or "")).casefold()


def resolve_conditions(jobs) -> list[dict]:
    """BROKEN->OK half. Clears every broken condition whose subject is in `jobs`; returns
    the cleared records that deserve a green signal (fleet=True and previously paged)."""
    recovered: list[dict] = []
    try:
        # A blank subject on either side would match every other blank — never.
        wanted = {n for n in (_norm_job(j) for j in jobs) if n}
        st = _load_alert_state()
        changed = False
        for k, rec in list(st.items()):
            subj = _norm_job((rec or {}).get("job"))
            if subj and subj in wanted and rec.get("status") == "broken":
                del st[k]
                changed = True
                if rec.get("fleet") and rec.get("paged"):
                    recovered.append(rec)
        if changed:
            write_json_atomic(ALERT_STATE, st)
    except Exception:  # noqa: BLE001
        pass
    return recovered


def open_issues() -> list[dict]:
    """Every broken condition with age_d (since first_seen) and quiet_d (since last
    re-asserted), oldest first. Read-only.

    AN UNREADABLE LEDGER IS NOT AN EMPTY LEDGER: a read failure is returned AS an open
    issue, because a consumer that hides the block when the list is empty would otherwise
    render a corrupt store exactly like "no open issues"."""
    out: list[dict] = []
    try:
        raw = ALERT_STATE.read_text(encoding="utf-8") if ALERT_STATE.exists() else "{}"
        st = json.loads(raw)
        if not isinstance(st, dict):
            raise ValueError(f"alert state is {type(st).__name__}, expected object")
    except (OSError, ValueError) as exc:
        return [{"job": "alert-state", "raised_by": "alert-state", "age_d": 0.0,
                 "last_seen": "", "quiet_d": None,
                 "message": f"UNREADABLE ({type(exc).__name__}: {exc}) — open issues "
                            f"cannot be reported; this line is the alarm"}]
    try:
        now_s = _clock()
        for rec in st.values():
            if (rec or {}).get("status") != "broken":
                continue
            # An unparseable first_seen falls back to last_seen, never to 0 ("just now").
            age = (_iso_age_s(rec.get("first_seen", ""), now_s)
                   or _iso_age_s(rec.get("last_seen", ""), now_s))
            quiet = _iso_age_s(rec.get("last_seen", ""), now_s)
            out.append({"job": rec.get("job", "?"), "message": rec.get("message", ""),
                        "raised_by": rec.get("raised_by", rec.get("job", "?")),
                        "age_d": (age or 0) / 86400.0,
                        "last_seen": rec.get("last_seen", ""),
                        "quiet_d": None if quiet is None else quiet / 86400.0})
        out.sort(key=lambda r: r["age_d"], reverse=True)
    except Exception as exc:  # noqa: BLE001
        out.append({"job": "alert-state", "raised_by": "alert-state", "age_d": 0.0,
                    "last_seen": "", "quiet_d": None,
                    "message": f"PARTIAL — {type(exc).__name__}: {exc}"})
    return out


def _post(text: str, title: str) -> None:
    """Best-effort Slack post through bin/notify_slack.py (which no-ops when no webhook is
    configured and scrubs again at its own egress). Never raises."""
    try:
        if str(REPO / "bin") not in sys.path:
            sys.path.insert(0, str(REPO / "bin"))
        from notify_slack import post_slack  # noqa: PLC0415
        post_slack(text, title=title)
    except Exception:  # noqa: BLE001
        pass


def _append_alerts_log(line: str) -> None:
    try:
        ALERTS_LOG.parent.mkdir(parents=True, exist_ok=True)
        with ALERTS_LOG.open("a", encoding="utf-8") as f:
            f.write(f"{_now_iso()} {line}\n")      # UTC-Z, same clock as the ledger
    except OSError:
        pass


def alert(job_name: str, message: str, log=None, *, fleet: bool = False,
          subject: str | None = None) -> None:
    """Surface an operational alert — STATE-AWARE. NEVER raises.

    Always appends to forge/alerts.log (the unthrottled audit trail). Posts to Slack only
    on OK->BROKEN and at chronic milestones; otherwise the condition stays visible through
    open_issues(). fleet=True lets self_loop's reconciliation post a green 'recovered' for
    it; subject=<job> when a watchdog raises a condition about a DIFFERENT job.

    Inert under set_dry_run(True): prints what would have fired, writes and pages nothing."""
    message = scrub_secrets(message)
    if _DRY_RUN:
        print(f"[dry-run:{_DRY_REASON}] would ALERT [{job_name}] {message}", file=sys.stderr)
        if log:
            log(f"[dry-run] ALERT [{job_name}] {message}")
        return
    _append_alerts_log(f"[{job_name}] {message}")
    stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(_clock()))
    if not mark_broken(job_name, message, fleet=fleet, subject=subject):
        due = _chronic_repage_due(job_name, message)
        if due is None:
            if log:
                log(f"ALERT [{job_name}] {message} (Slack suppressed — chronic, see open issues)")
            return
        _post(f"*{job_name}* — STILL BROKEN after {due}d — {message}\n_{stamp}_",
              title=f"harness still broken ({due}d)")
        if log:
            log(f"ALERT [{job_name}] {message} (chronic {due}d — re-paged)")
        return
    _post(f"*{job_name}* — {message}\n_{stamp}_", title="harness alert")
    if log:
        log(f"ALERT [{job_name}] {message}")


def alert_recovered(job_name: str, message: str, log=None) -> None:
    """Green BROKEN->OK signal. Emit only after resolve_conditions() confirmed a
    previously-paged FLEET condition cleared. NEVER raises; inert under dry-run."""
    message = scrub_secrets(message)
    if _DRY_RUN:
        print(f"[dry-run:{_DRY_REASON}] would RECOVER [{job_name}] {message}", file=sys.stderr)
        return
    _append_alerts_log(f"[{job_name}] RECOVERED: {message}")
    stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(_clock()))
    _post(f"*{job_name}* — {message}\n_{stamp}_", title="harness recovered")
    if log:
        log(f"RECOVERED [{job_name}] {message}")


# =====================================================================================
# Run audit + outcome sidecars
# =====================================================================================
def record_run(job: str, status: str = "ok", actions: int = 0,
               halt_reason: str | None = None, attention=None, db_path=None):
    """Record a completed autonomous run in the runner audit DB (forge/runner.db) so the
    daily digest shows it. FAIL-OPEN; inert in dry-run. Returns the run_id or None."""
    if _DRY_RUN:
        return None
    try:
        if str(REPO / "bin") not in sys.path:
            sys.path.insert(0, str(REPO / "bin"))
        from runner import events as _ev  # noqa: PLC0415
        rid = _ev.start_run(job, db_path=db_path)
        if actions:
            _ev.bump_run(rid, actions=actions, db_path=db_path)
        for item in (attention or []):
            _ev.log_event(rid, "needs_attention", status="warn", payload=str(item),
                          needs_attention=True, job=job, db_path=db_path)
        _ev.end_run(rid, status, halt_reason=halt_reason, db_path=db_path)
        return rid
    except Exception:  # noqa: BLE001
        return None


#: The outcome vocabulary self_loop understands. `empty` = ran correctly, nothing to do.
OUTCOME_STATUSES = ("ok", "empty", "transient", "auth_failed", "rate_limited", "error")
#: Statuses that mean "ran, and did NOT do its work".
FAILED_OUTCOMES = ("transient", "auth_failed", "rate_limited", "error")


def record_outcome(job: str, status: str = "ok", produced=None, detail: str = "") -> None:
    """Write forge/outcomes/<job>.json so the loop sees WHAT a job did, not just that it
    exited 0 (a job can exit 0 having done nothing because its login died). Also appends
    one line to forge/outcomes/history.jsonl so a slow degradation is visible as a trend.

    `job` must be the scheduler job id (bin/scheduler/jobs.py) — self_loop looks the
    sidecar up by that id. `produced` = count of things made this run; None means "not
    instrumented". status='ok' with produced=0 is a contract violation (a job that did
    nothing must say 'empty' or 'error') and raises an alert. FAIL-OPEN; inert in dry-run."""
    if _DRY_RUN:
        print(f"[dry-run:{_DRY_REASON}] would record_outcome({job}, status={status}, "
              f"produced={produced})", file=sys.stderr)
        return
    try:
        rec = {"ts": _now_iso(), "status": status, "produced": produced,
               "detail": scrub_secrets(str(detail))[:200]}
        write_json_atomic(OUTCOMES_DIR / f"{job}.json", rec)
        try:
            with (OUTCOMES_DIR / "history.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"job": job, **rec}) + "\n")
        except OSError:
            pass
        if status == "ok" and produced == 0:
            alert(job, f"reported status=ok but produced=0 — a job that did nothing must "
                       f"report 'empty' or 'error', not 'ok' ({str(detail)[:120]})")
    except Exception:  # noqa: BLE001
        pass


def read_outcome(job: str) -> dict | None:
    """A job's outcome sidecar plus `age_h`, or None if absent/unreadable.

    An unparseable timestamp yields age_h=None, never 0.0: collapsing "cannot be dated"
    into "0 hours old" made every consumer read an undatable sidecar as the freshest
    possible evidence."""
    try:
        p = OUTCOMES_DIR / f"{job}.json"
        if not p.exists():
            return None
        d = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(d, dict):
            return None
        age_s = _iso_age_s(d.get("ts", ""))
        d["age_h"] = None if age_s is None else age_s / 3600.0
        return d
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def require_fresh(producer: str, max_age_h: float, *, require_produced: bool = False,
                  consumer: str = "") -> tuple[bool, str]:
    """Freshness barrier for a job that CONSUMES another job's output. Returns (ok, reason).
    On (False, reason) the caller must exit NON-ZERO with the reason — `return 0` is what
    makes a total upstream outage look like a clean run.

      missing sidecar  -> not fresh (the producer never proved it ran)
      future timestamp -> not fresh (clock skew / hand edit — undatable, not fresh)
      age > max_age_h  -> not fresh
      ok | empty       -> fresh (require_produced=True also demands produced > 0)
      anything else    -> not fresh

    FAIL-OPEN on an internal error only: a barrier bug must not wedge the fleet."""
    try:
        oc = read_outcome(producer)
        who = f"{consumer}: " if consumer else ""
        if oc is None:
            return (False, f"{who}producer {producer} has no outcome sidecar — it has never "
                           f"recorded that it ran")
        age, status, produced = oc.get("age_h"), oc.get("status"), oc.get("produced")
        if age is None:
            return (False, f"{who}producer {producer} sidecar has no readable timestamp")
        if age < 0:
            return (False, f"{who}producer {producer} sidecar is timestamped {abs(age):.1f}h in "
                           f"the FUTURE — an outcome that cannot be dated is not evidence")
        if age > max_age_h:
            return (False, f"{who}producer {producer} last recorded an outcome {age:.1f}h ago "
                           f"(max {max_age_h}h) — its output is stale")
        if status not in ("ok", "empty"):
            return (False, f"{who}producer {producer} last run reported '{status}' — "
                           f"its output cannot be trusted")
        if require_produced and not produced:
            return (False, f"{who}producer {producer} ran {age:.1f}h ago but produced "
                           f"{produced!r} — nothing to consume")
        return (True, f"{who}producer {producer} ok ({status}, produced={produced!r}, "
                      f"{age:.1f}h ago)")
    except Exception as exc:  # noqa: BLE001
        return (True, f"require_fresh({producer}) check itself failed ({exc!r}) — fail-open")


_RESET_RE = re.compile(r"resets?\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)", re.IGNORECASE)


def parse_limit_reset(detail: str, anchor_iso: str | None = None):
    """Local naive datetime at which a usage-limit message says the limit lifts, else None.

    The CLI prints e.g. "You've hit your session limit · resets 5:10pm". self_loop reads it
    from the outcome sidecar so it stops re-running a rate-limited job before the reset —
    retrying into a live limit spends the same shared pool the operator is working from.
    `anchor_iso` is the sidecar's UTC timestamp; a clock time more than an hour before the
    anchor means the next day. Fail-closed: unparseable -> None."""
    if not detail:
        return None
    m = _RESET_RE.search(str(detail))
    if not m:
        return None
    try:
        hour = int(m.group(1)) % 12 + (12 if m.group(3).lower() == "pm" else 0)
        minute = int(m.group(2) or 0)
        if anchor_iso:
            anchor = datetime.datetime.fromisoformat(str(anchor_iso).replace("Z", "+00:00"))
            anchor = anchor.astimezone().replace(tzinfo=None)
        else:
            anchor = datetime.datetime.fromtimestamp(_clock())
        cand = anchor.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if cand < anchor - datetime.timedelta(hours=1):
            cand += datetime.timedelta(days=1)
        return cand
    except (ValueError, TypeError, OverflowError):
        return None


# =====================================================================================
# Single-instance lock
# =====================================================================================
def _pid_alive(pid: int) -> bool:
    """True if `pid` is a live process. FAIL-CLOSED: if we cannot tell, report alive so a
    lock is never stolen from a running job.

    POSIX: signal-0 probe. Windows: OpenProcess + GetExitCodeProcess via ctypes (no shell)."""
    if pid <= 0:
        return True
    try:
        if os.name == "nt":
            import ctypes  # noqa: PLC0415
            from ctypes import wintypes  # noqa: PLC0415
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            k32.OpenProcess.restype = wintypes.HANDLE
            h = k32.OpenProcess(0x1000, False, int(pid))   # QUERY_LIMITED_INFORMATION
            if not h:
                # 87 = ERROR_INVALID_PARAMETER: no such process. Anything else (e.g. access
                # denied) means it exists but may not be inspected.
                return ctypes.get_last_error() != 87
            try:
                code = wintypes.DWORD()
                if not k32.GetExitCodeProcess(h, ctypes.byref(code)):
                    return True
                return code.value == 259                    # STILL_ACTIVE
            finally:
                k32.CloseHandle(h)
        os.kill(int(pid), 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except Exception:  # noqa: BLE001
        return True


@contextlib.contextmanager
def single_instance(job: str, stale_seconds: int = 6 * 3600):
    """`with single_instance("self-test") as ok:` — ok is True if this process holds the
    lock, False if another live run holds it (caller should exit 0).

    A lock older than stale_seconds, or whose recorded PID is gone (the process was killed
    and its `finally` never ran), is reclaimed. Without the PID check a killed run left a
    lock that made every retry exit 0 as a silent no-op for hours. FAIL-OPEN on lock-layer
    errors: a lock bug must never stop the job."""
    lock = LOCK_DIR / f"{job}.lock"
    held = False
    try:
        LOCK_DIR.mkdir(parents=True, exist_ok=True)
        try:
            if lock.exists():
                # wall-clock: an mtime is filesystem time, never the pinnable _clock
                aged = (time.time() - lock.stat().st_mtime) > stale_seconds
                orphan = False
                if not aged:
                    try:
                        raw = lock.read_text(encoding="ascii", errors="ignore").strip()
                        orphan = bool(raw) and not _pid_alive(int(raw))
                    except (OSError, ValueError):
                        orphan = False
                if aged or orphan:
                    lock.unlink()
        except OSError:
            pass
        try:
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode("ascii", "ignore"))
            os.close(fd)
            held = True
        except FileExistsError:
            yield False
            return
    except OSError:
        yield True
        return
    try:
        yield True
    finally:
        if held:
            try:
                lock.unlink()
            except OSError:
                pass


# =====================================================================================
# One structured `claude -p` call
# =====================================================================================
@dataclass
class ClaudeResult:
    ok: bool
    status: str            # ok | auth_failed | rate_limited | model_unavailable | error
                           # | refused | contract_failed | not_found | timeout
    value: dict | None = None
    error: str = ""
    raw: str = ""


def _claude_bin() -> str | None:
    import shutil  # noqa: PLC0415
    return shutil.which("claude") or shutil.which("claude.exe") or shutil.which("claude.cmd")


def _lenient_json(text: str):
    """Parse a JSON object, tolerating ``` fences and surrounding prose (outermost {...})."""
    if not text:
        return None
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    try:
        v = json.loads(t)
        return v if isinstance(v, dict) else None
    except ValueError:
        pass
    a, b = t.find("{"), t.rfind("}")
    if a != -1 and b > a:
        try:
            v = json.loads(t[a:b + 1])
            return v if isinstance(v, dict) else None
        except ValueError:
            return None
    return None


def _refused(stdout: str) -> bool:
    """The CLI's JSON envelope says stop_reason="refusal". A refusal is deterministic (the
    same prompt refuses again), so it is never treated as a transient failure."""
    if not stdout:
        return False
    if '"stop_reason":"refusal"' in stdout.replace(" ", ""):
        return True
    env = _lenient_json(stdout)
    return isinstance(env, dict) and env.get("stop_reason") == "refusal"


def _extract_value(stdout: str) -> dict | None:
    """The structured value from a `--output-format json` envelope: it may arrive as an
    object or as a JSON string, under `structured_output` or `result`."""
    env = _lenient_json(stdout)
    if env is None:
        return None
    if isinstance(env.get("structured_output"), dict):
        return env["structured_output"]
    if isinstance(env.get("result"), dict):
        return env["result"]
    if isinstance(env.get("result"), str):
        return _lenient_json(env["result"])
    return env if "result" not in env else None


# Windows caps a command line at ~32k chars and both the prompt and the inline schema
# would sit on argv; past that the launch fails with a misleading "filename too long".
# `claude -p` with no prompt argument reads the prompt from stdin, so large ones go there.
_SAFE_ARGV_CHARS = 8000


def claude_json(prompt: str, schema: dict, *, timeout_s: int = 300, tools: str | None = None,
                cwd: Path | None = None, runner=None) -> ClaudeResult:
    """One headless `claude -p --output-format json --json-schema <inline>` call on the
    SUBSCRIPTION (clean_env strips any metered key). The exit code is classified FIRST,
    then the output is parsed and the schema's required keys are checked. `runner` is
    injectable for tests (defaults to subprocess.run). Never raises."""
    exe = _claude_bin() if runner is None else "claude"
    if not exe:
        return ClaudeResult(False, "not_found", error="claude CLI not found on PATH")
    run = runner or subprocess.run
    schema_json = json.dumps(schema)
    via_stdin = (len(prompt) + len(schema_json)) > _SAFE_ARGV_CHARS
    cmd = [exe, "-p"] + ([] if via_stdin else [prompt])
    cmd += ["--output-format", "json", "--json-schema", schema_json]
    if tools:
        # The grant IS the enforcement: a node that only needs to read gets read tools only.
        cmd += ["--allowed-tools", tools]
    try:
        r = run(cmd, capture_output=True, text=True, timeout=timeout_s,
                env=clean_env(CLAUDE_BRAIN_SKIP_HOOKS="1"),
                cwd=str(cwd) if cwd else None,
                input=prompt if via_stdin else None,
                stdin=None if via_stdin else subprocess.DEVNULL,
                encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return ClaudeResult(False, "timeout", error=f"timed out after {timeout_s}s")
    except Exception as exc:  # noqa: BLE001
        return ClaudeResult(False, "error", error=repr(exc))
    out, err = r.stdout or "", r.stderr or ""
    if _refused(out):
        return ClaudeResult(False, "refused", error="model refused the request", raw=out[-2000:])
    status, detail = classify_claude_result(r.returncode, out, err)
    if status != "ok":
        return ClaudeResult(False, status, error=detail or "", raw=(out or err)[-2000:])
    value = _extract_value(out)
    if value is None:
        return ClaudeResult(False, "contract_failed", error="output was not JSON",
                            raw=out[-2000:])
    missing = [k for k in (schema.get("required") or []) if k not in value]
    if missing:
        return ClaudeResult(False, "contract_failed", value=value,
                            error=f"missing required keys: {missing}", raw=out[-2000:])
    return ClaudeResult(True, "ok", value=value, raw=out[-2000:])
