"""Tests for the pure parts of bin/gbrain_setup.py (no clone/install side effects)."""
import importlib.util
import sys
from pathlib import Path


def _load():
    p = Path(__file__).resolve().parents[1] / "gbrain_setup.py"
    s = importlib.util.spec_from_file_location("gbrain_setup", p)
    m = importlib.util.module_from_spec(s)
    sys.modules["gbrain_setup"] = m
    s.loader.exec_module(m)
    return m


gs = _load()


def test_mcp_args_shape():
    args = gs.mcp_args(Path("/home/u/.gbrain-tool"))
    assert args[0] == "add-mcp"
    assert "--name" in args and "gbrain" in args
    assert "--command" in args and "bun" in args
    # cli.ts path + serve are passed as --arg values
    assert any(a.endswith("cli.ts") for a in args)
    assert "serve" in args
    assert any(a.startswith("OLLAMA_HOST=") for a in args)


def test_check_mode_no_side_effects(tmp_path, monkeypatch, capsys):
    # Pretend all deps exist; --check must not clone/install (no git/bun calls).
    monkeypatch.setattr(gs, "detect", lambda t: True)
    called = {"run": 0}
    monkeypatch.setattr(gs.subprocess, "run", lambda *a, **k: called.__setitem__("run", called["run"] + 1))
    rc = gs.main(["--dir", str(tmp_path / "gb")])  # no --apply
    assert rc == 0
    assert called["run"] == 0  # nothing executed in check mode
    assert "--check OK" in capsys.readouterr().out
