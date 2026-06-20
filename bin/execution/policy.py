"""Confirmation policy: maps (action_class x risk-level) -> AUTO / PAUSE / NEVER.

The POLICY decides, never the model. A class only reaches AUTO if it is explicitly
enabled (an edit to forge/execution_policy.json = the operator's per-class sign-off).
A disabled class can never reach AUTO no matter how low the risk. The policy file is
on the always-deny-write list (a confined action cannot edit its own guardrails).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

POLICY_PATH = Path(__file__).resolve().parents[2] / "forge" / "execution_policy.json"

# v1 defaults. enabled=True for read_external only.
DEFAULT_POLICY: dict[str, dict] = {
    "read_external":   {"enabled": True,  "LOW": "AUTO",  "MED": "PAUSE", "HIGH": "PAUSE"},
    "write_workspace": {"enabled": False, "LOW": "PAUSE", "MED": "PAUSE", "HIGH": "NEVER"},
    "run_script":      {"enabled": False, "LOW": "PAUSE", "MED": "PAUSE", "HIGH": "NEVER"},
    "act_web":         {"enabled": False, "LOW": "PAUSE", "MED": "PAUSE", "HIGH": "NEVER"},
    # post / send / account creation / financial — never autonomous until deliberately enabled.
    "external_mutate": {"enabled": False, "LOW": "NEVER", "MED": "NEVER", "HIGH": "NEVER"},
}


@dataclass
class Decision:
    action: str   # AUTO | PAUSE | NEVER
    reason: str


def load_policy(path=None) -> dict:
    p = Path(path or POLICY_PATH)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            pass
    return DEFAULT_POLICY


def decide(risk, action_class: str, policy: dict | None = None) -> Decision:
    policy = policy if policy is not None else load_policy()
    cls = policy.get(action_class)
    if cls is None:
        return Decision("NEVER", f"unknown action_class '{action_class}'")
    gate = cls.get(risk.level, "NEVER")
    if not cls.get("enabled", False):
        # Disabled class: never AUTO. AUTO downgrades to PAUSE; NEVER stays NEVER.
        if gate == "AUTO":
            gate = "PAUSE"
        return Decision(gate, f"class '{action_class}' not enabled (risk {risk.level})")
    return Decision(gate, f"class '{action_class}' enabled, risk {risk.level} -> {gate}")
