"""The orchestrator: score -> policy-gate -> (NEVER refuse | PAUSE park | AUTO run),
every branch logged to runner.db post-redaction, the AUTO branch under the harness
RunGuard + a swappable backend.

    execute(action) -> {run_id, action, risk, decision, status, result, approval_id?}

A parked action is resumed by calling execute() again with approved_id=<its row>:
if the operator approved that exact action, it runs once and the approval is spent.

status: 'done' (ran ok) | 'pending' (parked for approval) | 'refused' (NEVER) |
        'blocked' (egress denied) | 'error' (action raised).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runner import events  # noqa: E402

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


def _log(run_id, etype, status, payload, *, needs_attention=False,
         job="execution", db_path=None):
    body = payload if isinstance(payload, str) else json.dumps(payload, default=str)
    events.log_event(run_id, etype, status, payload=redaction.scrub(body),
                     needs_attention=needs_attention, job=job, db_path=db_path)


def execute(action, *, run_id=None, db_path=None, policy_cfg=None,
            backend=None, guard=None, job="execution", approved_id=None) -> dict:
    backend = backend or LocalBackend()
    own_run = run_id is None
    if own_run:
        run_id = events.start_run(job, db_path=db_path)

    risk = score_action(action)
    decision = policy.decide(risk, action.action_class, policy=policy_cfg)
    base = {"run_id": run_id, "action": getattr(action, "name", "?"),
            "risk": risk.level, "decision": decision.action}

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
    resumed = False
    if decision.action == "PAUSE" and approved_id is not None:
        row = approval.get(approved_id, db_path=db_path)
        if (row and row["status"] == "approved" and row["summary"] == action.summary()
                and row["action_class"] == action.action_class
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

    # AUTO
    if guard is not None:
        guard.check()
    result = None
    status = "done"
    try:
        result = backend.run(action)
        _log(run_id, "action:done", "ok",
             {"action": base["action"], "result": _safe(result)}, job=job, db_path=db_path)
    except EgressDenied as e:
        status = "blocked"
        _log(run_id, "action:blocked", "blocked",
             {"action": base["action"], "error": str(e)},
             needs_attention=True, job=job, db_path=db_path)
    except Exception as e:  # noqa: BLE001 — record + continue, mirror runner
        status = "error"
        _log(run_id, "action:error", "error",
             {"action": base["action"], "error": str(e)},
             needs_attention=True, job=job, db_path=db_path)
    if guard is not None:
        guard.record()
    if own_run:
        events.end_run(run_id, "done", db_path=db_path)
    return {**base, "status": status, "result": result}
