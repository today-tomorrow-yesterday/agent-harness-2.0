"""sync-agent-tools.py: one manifest applied to every seat, gated, touching only managed things.

The behaviours pinned here are the ones whose failure is silent: a skill copied without its
references/ directory, a re-run that duplicates a TOML table, a hand-written config line lost on
rewrite, a broken skill shipped to every seat at once.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

BIN = Path(__file__).resolve().parents[1]
REPO = BIN.parent


def _load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, str(BIN / file))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sat = _load("sync_agent_tools", "sync-agent-tools.py")


def make_skill(root: Path, name: str, extra: dict[str, str] | None = None,
               frontmatter: str | None = None) -> Path:
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    fm = frontmatter if frontmatter is not None else f"---\nname: {name}\ndescription: x.\n---\n"
    (d / "SKILL.md").write_text(fm + "\n# body\n", encoding="utf-8")
    for rel, text in (extra or {}).items():
        p = d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return d


SERVERS = {"demo": {"command": "npx", "args": ["-y", "demo-mcp"], "env": {"TOKEN": "abc"}}}


# ------------------------------------------------------------------ paths + manifest

def test_relative_paths_resolve_against_the_repo_not_the_cwd(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    assert sat.resolve_path("skills/x") == REPO / "skills" / "x"


def test_home_and_env_vars_expand(monkeypatch, tmp_path):
    monkeypatch.setenv("SEAT_ROOT", str(tmp_path))
    assert sat.resolve_path("$SEAT_ROOT/a") == tmp_path / "a"
    assert sat.resolve_path("~/x") == Path.home() / "x"


def test_skill_source_may_name_the_dir_or_its_skill_md(tmp_path):
    assert sat.skill_source_dir({"source": str(tmp_path / "s" / "SKILL.md")}) == tmp_path / "s"
    assert sat.skill_source_dir({"source": str(tmp_path / "s")}) == tmp_path / "s"


def test_shipped_example_manifest_parses_and_every_skill_source_exists():
    pytest.importorskip("yaml")
    m = sat.load_manifest(sat.EXAMPLE_MANIFEST)
    assert m["seats"], "the example must show at least one seat"
    for name, spec in m["skills"].items():
        src = sat.skill_source_dir(spec)
        assert (src / "SKILL.md").is_file(), f"example manifest names missing skill {name}"
        assert sat.gate_skill(name, src) == [], name
    for name in m.get("not_installed_by_design") or {}:
        assert (REPO / "skills" / name).is_dir(), name


def test_disabled_seats_are_skipped():
    m = {"seats": {"a": {"kind": "codex"}, "b": {"kind": "codex", "enabled": False}}}
    assert list(sat.enabled_seats(m)) == ["a"]
    assert list(sat.enabled_seats(m, only="b")) == []


def test_unset_env_reference_is_kept_visible_not_emptied(monkeypatch, capsys):
    monkeypatch.delenv("NOPE_NOT_SET", raising=False)
    assert sat.expand_env_values({"K": "${NOPE_NOT_SET}"}) == {"K": "${NOPE_NOT_SET}"}
    assert "unset variable" in capsys.readouterr().err


def test_env_reference_expands_from_the_environment(monkeypatch):
    monkeypatch.setenv("DEMO_SECRET", "s3")
    assert sat.expand_env_values({"K": "${DEMO_SECRET}"}) == {"K": "s3"}


# ------------------------------------------------------------------ gate

def test_gate_passes_a_good_skill(tmp_path):
    src = make_skill(tmp_path, "good", {"helper.py": "x = 1\n"})
    assert sat.gate_skill("good", src) == []


def test_gate_rejects_bad_frontmatter_and_uncompilable_helper(tmp_path):
    src = make_skill(tmp_path, "bad", {"helper.py": "def broken(:\n"}, frontmatter="# no fm\n")
    problems = sat.gate_skill("bad", src)
    assert any("frontmatter" in p for p in problems)
    assert any("helper.py does not compile" in p for p in problems)


def test_gate_rejects_name_directory_mismatch(tmp_path):
    src = make_skill(tmp_path, "dir-name", frontmatter="---\nname: other\ndescription: x.\n---\n")
    assert any("directory" in p for p in sat.gate_skill("dir-name", src))


def test_gate_reports_a_missing_source(tmp_path):
    assert "does not exist" in sat.gate_skill("ghost", tmp_path / "ghost")[0]


def test_failed_gate_touches_no_seat(tmp_path):
    src = make_skill(tmp_path / "src", "bad", frontmatter="no frontmatter\n")
    seat_dir = tmp_path / "seat"
    mf = tmp_path / "m.json"
    mf.write_text(json.dumps({
        "seats": {"g": {"kind": "gemini", "settings_file": str(seat_dir / "settings.json"),
                        "skills_dir": str(seat_dir / "skills")}},
        "skills": {"bad": {"source": str(src)}}}), encoding="utf-8")
    assert sat.main(["--manifest", str(mf)]) == 1
    assert not seat_dir.exists(), "a failed gate must not write anything"


# ------------------------------------------------------------------ skill mirroring

def test_whole_skill_directory_travels_not_just_skill_md(tmp_path):
    src = make_skill(tmp_path / "src", "s", {"references/guide.md": "g", "tool.py": "x=1\n"})
    dest = tmp_path / "seat" / "s"
    sat.mirror_skill(src, dest, dry_run=False)
    assert (dest / "references" / "guide.md").read_text(encoding="utf-8") == "g"
    assert (dest / "tool.py").is_file()


def test_mirror_removes_deleted_files_but_keeps_sidecars_and_local_installs(tmp_path):
    src = make_skill(tmp_path / "src", "s", {"old.md": "o"})
    dest = tmp_path / "seat" / "s"
    sat.mirror_skill(src, dest, dry_run=False)
    (src / "old.md").unlink()
    (dest / "agents").mkdir()
    (dest / "agents" / "openai.yaml").write_text("x", encoding="utf-8")
    (dest / "node_modules" / "pkg").mkdir(parents=True)
    (dest / "node_modules" / "pkg" / "index.js").write_text("x", encoding="utf-8")
    res = sat.mirror_skill(src, dest, dry_run=False, keep={"agents/openai.yaml"})
    assert res["removed"] == ["old.md"]
    assert not (dest / "old.md").exists()
    assert (dest / "agents" / "openai.yaml").is_file()
    assert (dest / "node_modules" / "pkg" / "index.js").is_file()


def test_mirror_never_ships_junk(tmp_path):
    src = make_skill(tmp_path / "src", "s", {"__pycache__/x.pyc": "c", "notes.md.bak-1": "b",
                                             "node_modules/a.js": "n"})
    dest = tmp_path / "seat" / "s"
    sat.mirror_skill(src, dest, dry_run=False)
    shipped = sorted(p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file())
    assert shipped == ["SKILL.md"]


def test_dry_run_mirror_writes_nothing(tmp_path):
    src = make_skill(tmp_path / "src", "s")
    dest = tmp_path / "seat" / "s"
    res = sat.mirror_skill(src, dest, dry_run=True)
    assert res["copied"] == ["SKILL.md"] and not dest.exists()


def test_second_mirror_is_a_no_op(tmp_path):
    src = make_skill(tmp_path / "src", "s", {"r.md": "r"})
    dest = tmp_path / "seat" / "s"
    sat.mirror_skill(src, dest, dry_run=False)
    assert sat.mirror_skill(src, dest, dry_run=False) == {"copied": [], "removed": []}


# ------------------------------------------------------------------ codex

def test_codex_first_run_appends_block_and_keeps_user_config():
    text = 'model = "o4"\n\n[profiles.fast]\nmodel = "mini"\n'
    out = sat.merge_codex_config(text, {"mcp_servers": SERVERS})
    assert out.startswith('model = "o4"')
    assert "[profiles.fast]" in out
    assert out.count("[mcp_servers.demo]") == 1
    assert 'TOKEN = "abc"' in out


def test_codex_first_run_replaces_an_unmarked_hand_added_table():
    text = '[mcp_servers.demo]\ncommand = "old"\n\n[mcp_servers.demo.env]\nX = "1"\n'
    out = sat.merge_codex_config(text, {"mcp_servers": SERVERS})
    assert out.count("[mcp_servers.demo]") == 1, "duplicate tables make config.toml unparseable"
    assert 'command = "old"' not in out


def test_codex_rerun_is_idempotent_and_preserves_text_after_block():
    once = sat.merge_codex_config("a = 1\n", {"mcp_servers": SERVERS}) + "\n[tail]\nb = 2\n"
    twice = sat.merge_codex_config(once, {"mcp_servers": SERVERS})
    assert twice == sat.merge_codex_config(twice, {"mcp_servers": SERVERS})
    assert "[tail]" in twice and "a = 1" in twice


def test_codex_block_parses_as_toml_even_with_quotes_and_backslashes():
    tomllib = pytest.importorskip("tomllib")
    weird = {"w": {"command": 'tools\\x "y".exe', "args": ["--path", "a\\b"]}}
    data = tomllib.loads(sat.merge_codex_config("", {"mcp_servers": weird}))
    assert data["mcp_servers"]["w"]["command"] == 'tools\\x "y".exe'
    assert data["mcp_servers"]["w"]["args"] == ["--path", "a\\b"]


def test_codex_seat_writes_config_skills_and_sidecar(tmp_path):
    src = make_skill(tmp_path / "src", "s")
    m = {"mcp_servers": SERVERS, "skills": {"s": {"source": str(src), "codex_meta": {
        "display_name": "S", "short_description": "d", "default_prompt": "p"}}}}
    seat = {"config_file": str(tmp_path / "codex" / "config.toml"),
            "skills_dir": str(tmp_path / "codex" / "skills")}
    sat.sync_codex("codex", seat, m, dry_run=False)
    assert "[mcp_servers.demo]" in (tmp_path / "codex" / "config.toml").read_text(encoding="utf-8")
    assert (tmp_path / "codex" / "skills" / "s" / "SKILL.md").is_file()
    sidecar = tmp_path / "codex" / "skills" / "s" / "agents" / "openai.yaml"
    assert 'display_name: "S"' in sidecar.read_text(encoding="utf-8")
    sat.sync_codex("codex", seat, m, dry_run=False)
    assert sidecar.is_file(), "a second sync must not delete the sidecar it generated"


# ------------------------------------------------------------------ gemini

def test_gemini_merge_keeps_unmanaged_servers_and_other_keys():
    old = {"theme": "light", "mcpServers": {"mine": {"command": "x"}}}
    new = sat.merge_gemini_settings(old, {"mcp_servers": SERVERS})
    assert new["theme"] == "light"
    assert new["mcpServers"]["mine"] == {"command": "x"}
    assert new["mcpServers"]["demo"]["args"] == ["-y", "demo-mcp"]
    assert old["mcpServers"] == {"mine": {"command": "x"}}, "input must not be mutated"


def test_gemini_seat_creates_settings_when_absent(tmp_path):
    seat = {"settings_file": str(tmp_path / "g" / "settings.json"),
            "skills_dir": str(tmp_path / "g" / "skills")}
    sat.sync_gemini("g", seat, {"mcp_servers": SERVERS, "skills": {}}, dry_run=False)
    data = json.loads((tmp_path / "g" / "settings.json").read_text(encoding="utf-8"))
    assert "demo" in data["mcpServers"]


# ------------------------------------------------------------------ claude code

class FakeRunner:
    def __init__(self):
        self.calls = []

    def __call__(self, cmd, env):
        self.calls.append((cmd, env))
        return subprocess.CompletedProcess(cmd, 0, "", "")


def test_claude_seat_re_registers_servers_scoped_to_its_config_dir(tmp_path):
    src = make_skill(tmp_path / "src", "s")
    runner = FakeRunner()
    seat = {"config_dir": str(tmp_path / "profile")}
    m = {"mcp_servers": SERVERS, "skills": {"s": {"source": str(src)}}}
    sat.sync_claude_code("p", seat, m, dry_run=False, runner=runner)
    (rm_cmd, _rm_env), (add_cmd, add_env) = runner.calls
    assert rm_cmd[1:] == ["mcp", "remove", "demo", "-s", "user"]
    assert add_cmd[1:] == ["mcp", "add", "demo", "-s", "user", "-e", "TOKEN=abc", "--",
                           "npx", "-y", "demo-mcp"]
    assert add_env["CLAUDE_CONFIG_DIR"] == str(tmp_path / "profile")
    assert (tmp_path / "profile" / "skills" / "s" / "SKILL.md").is_file()


def test_claude_seat_dry_run_runs_nothing(tmp_path):
    runner = FakeRunner()
    sat.sync_claude_code("p", {"config_dir": str(tmp_path / "p")},
                         {"mcp_servers": SERVERS, "skills": {}}, dry_run=True, runner=runner)
    assert runner.calls == []


# ------------------------------------------------------------------ contract

def test_contract_render_stamps_hash_overwrites_hand_edits_and_backs_up(tmp_path):
    src = tmp_path / "AGENTS.md"
    src.write_text("# Rules\n\n1. be careful\n", encoding="utf-8")
    dest = tmp_path / "seat" / "CLAUDE.md"
    m = {"contract": {"source": str(src), "targets": {
        "p": {"enabled": True, "file": str(dest), "header": "# Seat p"}}}}
    assert sat.sync_contract(m, dry_run=False) == 0
    text = dest.read_text(encoding="utf-8")
    assert text.startswith("# Seat p") and "contract-sha256:" in text and "1. be careful" in text
    dest.write_text(text + "hand edit\n", encoding="utf-8")
    sat.sync_contract(m, dry_run=False)
    assert dest.read_text(encoding="utf-8") == text
    assert (tmp_path / "seat" / "CLAUDE.md.bak-contract").is_file()


def test_contract_disabled_target_is_not_written(tmp_path):
    src = tmp_path / "AGENTS.md"
    src.write_text("x", encoding="utf-8")
    dest = tmp_path / "GEMINI.md"
    m = {"contract": {"source": str(src), "targets": {"g": {"enabled": False, "file": str(dest)}}}}
    sat.sync_contract(m, dry_run=False)
    assert not dest.exists()


def test_contract_missing_source_is_an_error(tmp_path):
    m = {"contract": {"source": str(tmp_path / "absent.md"), "targets": {}}}
    assert sat.sync_contract(m, dry_run=False) == 1


# ------------------------------------------------------------------ end to end

def test_main_end_to_end_with_json_manifest(tmp_path):
    src = make_skill(tmp_path / "src", "s", {"references/r.md": "r"})
    mf = tmp_path / "m.json"
    mf.write_text(json.dumps({
        "seats": {"g": {"kind": "gemini", "settings_file": str(tmp_path / "g" / "settings.json"),
                        "skills_dir": str(tmp_path / "g" / "skills")},
                  "future": {"kind": "not-a-real-kind"}},
        "mcp_servers": SERVERS,
        "skills": {"s": {"source": str(src)}}}), encoding="utf-8")
    assert sat.main(["--manifest", str(mf), "--dry-run"]) == 0
    assert not (tmp_path / "g").exists(), "dry run wrote files"
    assert sat.main(["--manifest", str(mf)]) == 0
    assert (tmp_path / "g" / "skills" / "s" / "references" / "r.md").is_file()


def test_unknown_seat_name_is_an_error(tmp_path):
    mf = tmp_path / "m.json"
    mf.write_text(json.dumps({"seats": {}, "skills": {}}), encoding="utf-8")
    assert sat.main(["--manifest", str(mf), "--seat", "nope"]) == 2


def test_missing_default_manifest_explains_how_to_create_it(monkeypatch, tmp_path):
    monkeypatch.setattr(sat, "DEFAULT_MANIFEST", tmp_path / "nope.yaml")
    with pytest.raises(SystemExit) as e:
        sat.find_manifest(None)
    assert "agent-tools.example.yaml" in str(e.value)
