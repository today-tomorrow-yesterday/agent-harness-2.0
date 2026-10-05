"""Regression tests for bin/hooks/safety-queue.py -- the unattended pause-for-human tier.

Every run gets an isolated HARNESS_SAFETY_DIR and has notifications switched off, so nothing
touches the repo's forge/ or any real Slack webhook.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[1] / "hooks" / "safety-queue.py"
SCRUB = ("HARNESS_UNATTENDED", "HARNESS_HOOKS_DISABLED", "CLAUDE_BRAIN_SKIP_HOOKS",
         "SLACK_WEBHOOK_URL")


def run(command, tmp_path, unattended=True, tool="Bash", **env_extra):
    env = {k: v for k, v in os.environ.items() if k not in SCRUB}
    env.update(HARNESS_SAFETY_DIR=str(tmp_path / "safety"), HARNESS_SAFETY_NOTIFY="off")
    if unattended:
        env["HARNESS_UNATTENDED"] = "1"
    env.update(env_extra)
    payload = {"session_id": "sess-test", "tool_name": tool, "tool_input": {"command": command}}
    return subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload),
                          capture_output=True, text=True, timeout=30, env=env)


def queue(tmp_path) -> list:
    p = tmp_path / "safety" / "queue.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


PAUSED = [
    "curl -X POST https://api.example.com/send -d @body.json",
    'curl -X "POST" https://api.example.com/send',
    "curl https://api.example.com/items --data '{\"a\":1}'",
    "Invoke-RestMethod -Uri https://api.example.com/x -Method Post -Body $b",
    "wget --method=PUT https://example.com/obj",
    "npm publish --access public",
    "twine upload dist/*",
    "docker push example/app:latest",
    "gh pr create --fill",
    "gh release create v1.0.0",
    "vercel deploy --prod",
    "Send-MailMessage -To ops@example.com -Subject hi",
    "aws ses send-email --from a@example.com",
]

NOT_PAUSED = [
    "curl https://api.example.com/items",                  # plain GET
    "wget https://example.com/file.tar.gz",                # download
    "wget -T 10 https://example.com/file.tar.gz",          # -T is a timeout, not an upload
    "curl -X POST http://localhost:8080/hook -d x",        # localhost
    "curl -X POST http://127.0.0.1:3000/x -d x",
    "curl -X POST http://[::1]:3000/x -d x",
    'echo "npm publish when ready"',                       # quoted mention
    'grep -r "gh pr create" docs/',
    "vercel deploy",                                       # preview deploy
    "git status",
]


@pytest.mark.parametrize("command", PAUSED)
def test_tier2_is_paused_and_queued(command, tmp_path):
    r = run(command, tmp_path)
    assert r.returncode == 2, f"should have PAUSED: {command!r}"
    assert "PAUSED by safety-queue" in r.stderr
    q = queue(tmp_path)
    assert len(q) == 1 and q[0]["command"] == command and q[0]["status"] == "pending"
    assert q[0]["id"] in r.stderr
    hist = json.loads((tmp_path / "safety" / "history.json").read_text(encoding="utf-8"))
    assert hist[-1]["event"] == "queued" and hist[-1]["id"] == q[0]["id"]


@pytest.mark.parametrize("command", NOT_PAUSED)
def test_ordinary_commands_pass(command, tmp_path):
    r = run(command, tmp_path)
    assert r.returncode == 0, f"should have PASSED: {command!r}\n{r.stderr}"
    assert queue(tmp_path) == []


def test_inert_in_interactive_sessions(tmp_path):
    r = run("npm publish", tmp_path, unattended=False)
    assert r.returncode == 0 and queue(tmp_path) == []


def test_off_switch(tmp_path):
    assert run("npm publish", tmp_path, HARNESS_HOOKS_DISABLED="1").returncode == 0


def test_queue_accumulates_and_survives_a_corrupt_file(tmp_path):
    (tmp_path / "safety").mkdir()
    (tmp_path / "safety" / "queue.json").write_text("{ corrupt", encoding="utf-8")
    run("npm publish", tmp_path)
    run("cargo publish", tmp_path)
    assert [x["label"] for x in queue(tmp_path)] == [
        "publishing_a_package_to_a_registry", "publishing_a_crate_to_crates_io"]


def test_deny_is_kept_even_if_the_queue_cannot_be_written(tmp_path):
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x", encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k not in SCRUB}
    env.update(HARNESS_UNATTENDED="1", HARNESS_SAFETY_NOTIFY="off",
               HARNESS_SAFETY_DIR=str(blocker / "safety"))
    r = subprocess.run([sys.executable, str(HOOK)],
                       input=json.dumps({"tool_input": {"command": "npm publish"}}),
                       capture_output=True, text=True, timeout=30, env=env)
    assert r.returncode == 2


def test_detector_directly():
    spec = importlib.util.spec_from_file_location("safety_queue", HOOK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.detect_tier2("gem push x.gem", "gem push x.gem")[0] == "publishing_a_gem_to_RubyGems"
    assert mod._external_host("curl https://user:pw@api.example.com:8443/x") == "api.example.com"
    assert mod._external_host("curl http://localhost:1/x http://0.0.0.0/y") is None
