"""Kill-switch + budget (brakes) for the safety harness.

Halts a run when the STOP file exists, or the action count / cost ceiling is hit.
Pure logic except the single stop_file.exists() check — unit-testable with a tmp
stop_file and injected counters.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_STOP = Path(__file__).resolve().parents[2] / "forge" / "STOP"


class Halted(Exception):
    """Raised when a run must stop (kill-switch or ceiling)."""


@dataclass
class RunGuard:
    run_id: str
    max_actions: int = 20
    max_cost: float = 0.0  # 0 = no cost ceiling; action-count is the primary brake
    max_seconds: float = 0.0  # 0 = no wall-clock limit
    stop_file: Path = field(default_factory=lambda: DEFAULT_STOP)
    actions: int = 0
    cost: float = 0.0
    started: float = field(default_factory=time.time)

    def check(self) -> None:
        """Call BEFORE each step. Raises Halted if the run must not continue."""
        if Path(self.stop_file).exists():
            raise Halted("STOP file present")
        if self.actions >= self.max_actions:
            raise Halted(f"max_actions {self.max_actions} reached")
        if self.max_cost and self.cost >= self.max_cost:
            raise Halted(f"max_cost {self.max_cost} reached")
        if self.max_seconds and (time.time() - self.started) >= self.max_seconds:
            raise Halted(f"max_seconds {self.max_seconds} reached")

    def record(self, cost: float = 0.0) -> None:
        """Call AFTER each step."""
        self.actions += 1
        self.cost += cost
