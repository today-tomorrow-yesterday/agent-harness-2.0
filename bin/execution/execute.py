"""The orchestrator: score -> policy-gate -> (NEVER refuse | PAUSE park | AUTO run),
every branch logged to runner.db post-redaction, the AUTO branch under the harness
RunGuard + a swappable backend.

    execute(action) -> {run_id, action, risk, decision, status, result, approval_id?}

A parked action is resumed by calling execute() again with approved_id=<its row>:
if the operator approved that exact action, it runs once and the approval is spent.

status: 'done' (ran ok) | 'pending' (parked for approval) | 'refused' (NEVER) |
        'blocked' (egress denied) | 'error' (action raised) |
        'halted' (kill-switch engaged around the action, own run only).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runner import events  # noqa: E402
from runner.guard import Halted  # noqa: E402

from execution import approval, policy, redaction  # noqa: E402
from execution.backends import LocalBackend  # noqa: E402
from execution.risk import score_action  # noqa: E402

try:
    from execution.actions.read_web import EgressDenied
except Exception:  # noqa: BLE001
    class EgressDenied(Exception):  # type: ignore
        ...


def _safe(out) -> str:
    return str(out)[:2000]


def _caller() -> str:
    """Best-effort id of the calling code (first stack frame outside the execution
    package) as 'file.py:lineno' — for the per-invocation audit log. Never raises."""
    try:
        import inspect
        pkg = str(Path(__file__).resolve().parent)
        for fr in inspect.stack()[1:]:
            fp = str(Path(fr.filename).resolve())
            if not fp.startswith(pkg):
                return f"{Path(fp).name}:{fr.lineno}"
    except Exception:  # noqa: BLE001 — audit metadata must never break the gate
        pass
    return "?"


def _log(run_id, etype, status, payload, *, needs_attention=False,
         job="execution", db_path=None):
    body = payload if isinstance(payload, str) else json.dumps(payload, default=str)
    events.log_event(run_id, etype, status, payload=redaction.scrub(body),
                     needs_attention=needs_attention, job=job, db_path=db_path)


def _stop_engaged(guard) -> bool:
    """Is the kill-switch file present? Reads the guard's own stop_file, so a test
    guard pointed at a tmp STOP file is honoured."""
    stop_file = getattr(guard, "stop_file", None)
    return bool(stop_file) and Path(stop_file).exists()


def execute(action, *, run_id=None, db_path=None, policy_cfg=None,
            backend=None, guard=None, job="execution", approved_id=None) -> dict:
    backend = backend or LocalBackend()
    own_run = run_id is None
    if own_run:
        run_id = events.start_run(job, db_path=db_path)

    # Intercept-per-call: when policy_cfg is None (the production path) the policy is
    # re-read from disk inside policy.decide() on EVERY invocation, so an edit to
    # forge/execution_policy.json takes effect on the very next action, never only at
    # startup. policy_cfg exists for tests; the audit event flags its use.
    #
    # Full invocation logging: EVERY execute() call gets an action:invoke event
    # (action class, target, risk, decision, caller) BEFORE any branch runs, so no
    # path — refuse, park, run, error — is invisible. A crash in scoring / deciding /
    # summary() is ALSO logged (invoke with status error) and an owned run row is
    # closed before re-raising: the gate never fails invisibly or leaves a zombie.
    try:
        risk = score_action(action)
        decision = policy.decide(risk, action.action_class, policy=policy_cfg)
        base = {"run_id": run_id, "action": getattr(action, "name", "?"),
                "risk": risk.level, "decision": decision.action}
        _log(run_id, "action:invoke", "ok",
             {"action": base["action"], "action_class": getattr(action, "action_class", "?"),
              "target": action.summary(), "risk": risk.level, "reasons": risk.reasons,
              "decision": decision.action, "why": decision.reason, "caller": _caller(),
              "policy_source": "fresh-load" if policy_cfg is None else "caller-supplied"},
             job=job, db_path=db_path)
    except Exception as e:  # noqa: BLE001 — pre-branch failure: log, close run, raise
        try:
            _log(run_id, "action:invoke", "error",
                 {"action": getattr(action, "name", "?"),
                  "action_class": getattr(action, "action_class", "?"),
                  "caller": _caller(), "error": f"{type(e).__name__}: {e}"},
                 needs_attention=True, job=job, db_path=db_path)
        except Exception:  # noqa: BLE001 — best-effort; the original error must win
            pass
        if own_run:
            try:
                events.end_run(run_id, "error", db_path=db_path)
            except Exception:  # noqa: BLE001
                pass
        raise

    if decision.action == "NEVER":
        _log(run_id, "action:blocked", "blocked",
             {"action": base["action"], "risk": risk.level, "reasons": risk.reasons,
              "why": decision.reason}, needs_attention=True, job=job, db_path=db_path)
        if own_run:
            events.end_run(run_id, "done", db_path=db_path)
        return {**base, "status": "refused", "result": None}

    # RESUME: a parked action the operator has since approved runs once, on the
    # approval it was given. Only a PAUSE can be resumed — NEVER was refused above
    # and no approval overrides it. The approval must be for THIS action (same
    # summary + class, which is what the operator read) and is spent atomically.
    # The stored summary was scrubbed of secrets by approval.request(), so the text
    # comparison is scrubbed-to-scrubbed (comparing the raw summary would leave an
    # action whose summary carries a token un-resumable forever), and the row's
    # digest of the RAW summary pins the exact action (see approval.matches).
    resumed = False
    if decision.action == "PAUSE" and approved_id is not None:
        row = approval.get(approved_id, db_path=db_path)
        if (row and row["status"] == "approved"
                and approval.matches(row, action.summary(), action.action_class)
                and approval.consume(approved_id, db_path=db_path)):
            resumed = True
            base["decision"] = "APPROVED"
            _log(run_id, "action:resumed", "ok",
                 {"approval_id": approved_id, "action": base["action"],
                  "approved_by": row.get("resolved_by")}, job=job, db_path=db_path)

    if decision.action == "PAUSE" and not resumed:
        ap_id = approval.request(run_id, action.action_class, risk, action.summary(),
                                 payload={"action": base["action"]}, db_path=db_path)
        _log(run_id, "action:pending", "pending",
             {"approval_id": ap_id, "action": base["action"], "risk": risk.level,
              "why": decision.reason}, needs_attention=True, job=job, db_path=db_path)
        if own_run:
            events.end_run(run_id, "paused", db_path=db_path)
        return {**base, "status": "pending", "approval_id": ap_id, "result": None}

    # AUTO (or an approved resume)
    result = None
    status = "done"
    try:
        if guard is not None:
            guard.check()
        try:
            result = backend.run(action)
            _log(run_id, "action:done", "ok",
                 {"action": base["action"], "result": _safe(result)}, job=job, db_path=db_path)
        except EgressDenied as e:
            status = "blocked"
            _log(run_id, "action:blocked", "blocked",
                 {"action": base["action"], "error": str(e)},
                 needs_attention=True, job=job, db_path=db_path)
        except Halted:
            raise                       # a backend honouring the kill-switch is a halt, not an error
        except Exception as e:  # noqa: BLE001 — record + continue, mirror runner
            status = "error"
            _log(run_id, "action:error", "error",
                 {"action": base["action"], "error": str(e)},
                 needs_attention=True, job=job, db_path=db_path)
        if guard is not None:
            guard.record()
            # Re-check the kill-switch AFTER the action: bounds the check-then-act
            # race to the single action already in flight.
            if _stop_engaged(guard):
                raise Halted("STOP file present (post-action)")
    except Halted as e:
        # Never leave the run row stuck 'running'. End it if we own it; otherwise
        # propagate so the owning runner loop ends its run and stops the batch.
        _log(run_id, "action:halted", "halted",
             {"action": base["action"], "error": str(e)},
             needs_attention=True, job=job, db_path=db_path)
        if own_run:
            events.end_run(run_id, "halted", halt_reason=str(e), db_path=db_path)
            return {**base, "status": "halted", "result": result}
        raise
    if own_run:
        events.end_run(run_id, "done", db_path=db_path)
    return {**base, "status": status, "result": result}
