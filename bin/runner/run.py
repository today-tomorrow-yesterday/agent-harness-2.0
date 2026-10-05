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
    if resuming:
        # A step marked 'started' with no output means the previous attempt died
        # BETWEEN executing the step and persisting its result. Its side effect may be
        # half-applied, so surface it (needs_attention) instead of silently repeating
        # a commit / file write / Slack post.
        for idx in events.load_incomplete(run_id, db_path=db_path):
            events.log_event(run_id, f"step:{idx}", "warn",
                             payload="step started but never checkpointed -- the previous run "
                                     "died mid-step; its side effect may be partially applied. "
                                     "Re-running.",
                             needs_attention=True, job=job, db_path=db_path)
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
                events.begin_step(run_id, i, db_path=db_path)   # close the crash window
                out = step()
                if not events.save_checkpoint(run_id, i, out, db_path=db_path):
                    # Output is not JSON-serializable, so it was NOT checkpointed. The
                    # step succeeded but cannot be resumed past -- say so, don't pretend.
                    events.log_event(run_id, f"step:{i}", "warn",
                                     payload="step succeeded but its output is not "
                                             "JSON-serializable; no checkpoint written, so a "
                                             "resume will re-run it",
                                     needs_attention=True, job=job, db_path=db_path)
                events.log_event(run_id, f"step:{i}", "ok", payload=_safe(out),
                                 job=job, db_path=db_path)
                guard.record()
                results.append(out)
            except Halted:
                raise
            except Exception as e:  # noqa: BLE001 — record failure, keep going
                if type(e).__name__ == "Halted":
                    # The same Halted class can be imported under two module names
                    # (`guard` here, `runner.guard` inside execution.execute). A step
                    # that hit the kill-switch must stop the batch either way, not be
                    # recorded as an ordinary step error while the batch continues.
                    raise Halted(str(e)) from e
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
