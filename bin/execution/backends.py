"""Execution backends (the OpenHands `Workspace` shape): one interface, swappable
confinement. Agent/action code is identical regardless of where it runs.

- LocalBackend: run the action in-process. Used by v1 read_external (an outbound GET
  needs no sandbox beyond the egress allowlist enforced inside the action).
- ConfinedLocalBackend: STUB. The run_script / act_web classes will run here, under
  a sandbox model (bubblewrap + Landlock/seccomp + egress proxy). Not built until
  those classes are signed off per-class.
"""
from __future__ import annotations

from typing import Any


class LocalBackend:
    name = "local"

    def run(self, action) -> Any:
        return action.run()


class ConfinedLocalBackend:
    name = "confined-local"

    def run(self, action) -> Any:  # pragma: no cover - deferred
        raise NotImplementedError(
            "ConfinedLocalBackend (bubblewrap sandbox) is built when the "
            "run_script / act_web classes are signed off. v1 is read_external only.")
