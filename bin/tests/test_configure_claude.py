"""Unit tests for bin/configure_claude.py (cross-platform Claude config editor).

Loaded via importlib so the test runs regardless of package layout. All tests
use tmp paths / monkeypatch — the real ~/.claude.json is never touched.
"""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "configure_claude", Path(__file__).resolve().parents[1] / "configure_claude.py"
)
cc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cc)


def test_locate_config_prefers_env_override(tmp_path, monkeypatch):
    cfg = tmp_path / "custom.json"
    cfg.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_CONFIG_PATH", str(cfg))
    assert cc.locate_config() == cfg


def test_locate_config_defaults_to_home(tmp_path, monkeypatch):
    monkeypatch.delenv("CLAUDE_CONFIG_PATH", raising=False)
    monkeypatch.setattr(cc.Path, "home", staticmethod(lambda: tmp_path))
    assert cc.locate_config() == tmp_path / ".claude.json"


def test_write_config_has_no_bom_and_roundtrips(tmp_path):
    p = tmp_path / ".claude.json"
    cc.write_config(p, {"a": 1})
    raw = p.read_bytes()
    assert raw[:3] != b"\xef\xbb\xbf"  # no UTF-8 BOM
    assert cc.read_config(p) == {"a": 1}


def test_read_config_missing_returns_empty(tmp_path):
    assert cc.read_config(tmp_path / "nope.json") == {}


def test_add_mcp_server_is_idempotent():
    cfg = {}
    cc.add_mcp_server(cfg, "brain-server", "python3", ["server.py"], {})
    cc.add_mcp_server(cfg, "brain-server", "python3", ["server.py"], {})
    assert list(cfg["mcpServers"]) == ["brain-server"]
    assert cfg["mcpServers"]["brain-server"]["command"] == "python3"
    assert cfg["mcpServers"]["brain-server"]["args"] == ["server.py"]


def test_add_mcp_server_updates_existing():
    cfg = {"mcpServers": {"brain-server": {"command": "old", "args": []}}}
    cc.add_mcp_server(cfg, "brain-server", "python3", ["server.py"], {"X": "1"})
    assert cfg["mcpServers"]["brain-server"]["command"] == "python3"
    assert cfg["mcpServers"]["brain-server"]["env"] == {"X": "1"}


def test_add_hook_idempotent():
    cfg = {}
    cc.add_hook(cfg, "Stop", "python3 hooks/stop.py")
    cc.add_hook(cfg, "Stop", "python3 hooks/stop.py")
    stop = cfg["hooks"]["Stop"]
    cmds = [h["command"] for grp in stop for h in grp["hooks"]]
    assert cmds.count("python3 hooks/stop.py") == 1


def test_cli_dry_run_does_not_write(tmp_path, monkeypatch, capsys):
    cfg = tmp_path / ".claude.json"
    monkeypatch.setenv("CLAUDE_CONFIG_PATH", str(cfg))
    rc = cc.main(["add-mcp", "--name", "brain-server", "--command", "python3",
                  "--arg", "server.py", "--dry-run"])
    assert rc == 0
    assert not cfg.exists()  # dry-run wrote nothing
    assert "brain-server" in capsys.readouterr().out


def test_cli_add_mcp_writes(tmp_path, monkeypatch):
    cfg = tmp_path / ".claude.json"
    monkeypatch.setenv("CLAUDE_CONFIG_PATH", str(cfg))
    rc = cc.main(["add-mcp", "--name", "brain-server", "--command", "python3",
                  "--arg", "server.py"])
    assert rc == 0
    assert cc.read_config(cfg)["mcpServers"]["brain-server"]["command"] == "python3"


def test_cli_add_hook_writes(tmp_path, monkeypatch):
    cfg = tmp_path / ".claude.json"
    monkeypatch.setenv("CLAUDE_CONFIG_PATH", str(cfg))
    rc = cc.main(["add-hook", "--event", "Stop", "--command", "python3 stop.py"])
    assert rc == 0
    hooks = cc.read_config(cfg)["hooks"]["Stop"]
    assert hooks[0]["hooks"][0]["command"] == "python3 stop.py"
