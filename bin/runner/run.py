"""The harness wrapper: execute a job's steps sequentially WITH brakes + eyes.

`guard.check()` before each step, `log_event` + `guard.record()` after; step
errors are recorded (needs_attention) and the run continues; a STOP file or a
ceiling raises Halted and ends the run cleanly. Sequential only — the DAG /
checkpoint / termination-algebra Runner is a deferred later phase.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
import events  # noqa: E402
from guard import Halted, RunGuard  # noqa: E402


def _safe(out: Any) -> str:
    s = str(out)
    return s[:2000]


def run(job: str, steps: list[Callable[[], Any]], max_actions: int = 20,
        max_cost: float = 0.0, max_seconds: float = 0.0, stop_file=None,
        db_path=None, run_id: str | None = None) -> dict:
    """Execute steps with brakes + eyes. Pass an existing run_id to RESUME — already
    -checkpointed steps are skipped (their stored output is returned), so a crashed /
    STOP-halted long job continues instead of restarting."""
    resuming = run_id is not None
    done = events.load_checkpoints(run_id, db_path=db_path) if resuming else {}
    if not resuming:
        run_id = events.start_run(job, db_path=db_path)

    guard_kwargs = {"max_actions": max_actions, "max_cost": max_cost,
                    "max_seconds": max_seconds}
    if stop_file is not None:
        guard_kwargs["stop_file"] = Path(stop_file)
    guard = RunGuard(run_id, **guard_kwargs)
    guard.actions = len(done)  # completed steps count against the ceiling
    results: list[Any] = []
    status = "done"
    halt_reason = None

    try:
        for i, step in enumerate(steps):
            if i in done:                      # resume: skip already-completed step
                results.append(done[i])
                continue
            guard.check()
            try:
                out = step()
                events.save_checkpoint(run_id, i, out, db_path=db_path)
                events.log_event(run_id, f"step:{i}", "ok", payload=_safe(out),
                                 job=job, db_path=db_path)
                guard.record()
                results.append(out)
            except Halted:
                raise
            except Exception as e:  # noqa: BLE001 — record failure, keep going
                events.log_event(run_id, f"step:{i}", "error", payload=str(e),
                                 needs_attention=True, job=job, db_path=db_path)
                guard.record()
                results.append(None)
    except Halted as h:
        status, halt_reason = "halted", str(h)
        events.log_event(run_id, "halt", "halted", payload=str(h),
                         needs_attention=True, job=job, db_path=db_path)

    events.bump_run(run_id, actions=guard.actions - len(done), cost=guard.cost, db_path=db_path)
    events.end_run(run_id, status, halt_reason=halt_reason, db_path=db_path)
    return {"run_id": run_id, "status": status, "halt_reason": halt_reason,
            "actions": guard.actions, "results": results}
