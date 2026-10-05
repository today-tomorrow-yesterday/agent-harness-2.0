"""skill-sync-check.py: a read-only drift report that can see every way profiles disagree.

The case that matters most is the one a naive profile-vs-profile diff cannot see: a skill that is
missing from EVERY profile is absent from both sides of every comparison, so it reads as "in sync"
while being impossible to invoke anywhere.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

BIN = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("skill_sync_check", str(BIN / "skill-sync-check.py"))
ssc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ssc)


def put(root: Path, skill: str, files: dict[str, str]) -> None:
    for rel, text in files.items():
        p = root / skill / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")


def setup(tmp_path):
    canon, a, b = tmp_path / "canon", tmp_path / "a", tmp_path / "b"
    for r in (canon, a, b):
        r.mkdir()
    return canon, a, b


def test_identical_profiles_matching_canonical_are_in_sync(tmp_path):
    canon, a, b = setup(tmp_path)
    for root in (canon, a, b):
        put(root, "s", {"SKILL.md": "x", "references/r.md": "r"})
    r = ssc.analyse({"a": a, "b": b}, canon)
    assert r["in_sync"], r


def test_skill_missing_from_every_profile_is_unreachable(tmp_path):
    canon, a, b = setup(tmp_path)
    put(canon, "authored-never-installed", {"SKILL.md": "x"})
    r = ssc.analyse({"a": a, "b": b}, canon)
    assert r["unreachable"] == ["authored-never-installed"]
    assert not r["in_sync"]


def test_not_installed_by_design_is_not_a_defect(tmp_path):
    canon, a, b = setup(tmp_path)
    put(canon, "deliberate", {"SKILL.md": "x"})
    r = ssc.analyse({"a": a, "b": b}, canon, {"deliberate": "run from the repo only"})
    assert r["in_sync"] and r["not_installed_by_design"] == ["deliberate"]


def test_skill_in_one_profile_only_is_reported_missing_from_the_other(tmp_path):
    canon, a, b = setup(tmp_path)
    put(canon, "s", {"SKILL.md": "x"})
    put(a, "s", {"SKILL.md": "x"})
    r = ssc.analyse({"a": a, "b": b}, canon)
    assert r["missing"] == [{"skill": "s", "in": ["a"], "missing_from": ["b"]}]


def test_divergence_between_profiles_names_the_files(tmp_path):
    canon, a, b = setup(tmp_path)
    put(a, "s", {"SKILL.md": "v1", "only-a.md": "x"})
    put(b, "s", {"SKILL.md": "v2"})
    r = ssc.analyse({"a": a, "b": b}, None)
    d = r["diverged"][0]
    assert d["changed"] == ["SKILL.md"] and d["only_in_first"] == ["only-a.md"]


def test_copy_that_differs_from_canonical_is_stale_even_when_profiles_agree(tmp_path):
    """Both profiles carry the same OLD version: profile-vs-profile says fine, canonical does not."""
    canon, a, b = setup(tmp_path)
    put(canon, "s", {"SKILL.md": "new", "references/added.md": "r"})
    put(a, "s", {"SKILL.md": "old"})
    put(b, "s", {"SKILL.md": "old"})
    r = ssc.analyse({"a": a, "b": b}, canon)
    assert not r["diverged"]
    stale = {d["profile"]: d for d in r["stale_vs_canonical"]}
    assert set(stale) == {"a", "b"}
    assert stale["a"]["changed"] == ["SKILL.md"]
    assert stale["a"]["only_in_first"] == ["references/added.md"]


def test_junk_and_generated_sidecars_are_not_drift(tmp_path):
    canon, a, b = setup(tmp_path)
    put(canon, "s", {"SKILL.md": "x"})
    put(a, "s", {"SKILL.md": "x", "__pycache__/m.pyc": "c", "node_modules/p/i.js": "n"})
    put(b, "s", {"SKILL.md": "x", "agents/openai.yaml": "sidecar", "SKILL.md.bak-1": "old"})
    assert ssc.analyse({"a": a, "b": b}, canon)["in_sync"]


def test_underscore_and_dot_dirs_are_not_skills(tmp_path):
    canon, a, _b = setup(tmp_path)
    (canon / "_index").mkdir()
    (a / ".cache").mkdir()
    assert ssc.list_skills(canon) == set() and ssc.list_skills(a) == set()


def test_profiles_from_manifest_cover_every_seat_kind(tmp_path):
    m = {"seats": {
        "c": {"kind": "claude-code", "config_dir": str(tmp_path / "c")},
        "x": {"kind": "codex", "skills_dir": str(tmp_path / "x")},
        "off": {"kind": "claude-code", "config_dir": str(tmp_path / "o"), "enabled": False}}}
    got = ssc.profiles_from_manifest(m, Path)
    assert got == {"c": tmp_path / "c" / "skills", "x": tmp_path / "x"}


def test_cli_exit_codes_and_json(tmp_path, capsys):
    canon, a, b = setup(tmp_path)
    put(canon, "s", {"SKILL.md": "x"})
    put(a, "s", {"SKILL.md": "x"})
    put(b, "s", {"SKILL.md": "x"})
    args = ["--canonical", str(canon), "--profile", f"a={a}", "--profile", f"b={b}"]
    assert ssc.main(args) == 0
    capsys.readouterr()
    put(b, "s", {"SKILL.md": "changed"})
    assert ssc.main(args + ["--json"]) == 1
    assert json.loads(capsys.readouterr().out)["diverged"]
    assert ssc.main(["--profile", f"gone={tmp_path / 'nope'}"]) == 2


def test_report_leads_with_the_most_consequential_problem(tmp_path):
    canon, a, b = setup(tmp_path)
    put(canon, "unreached", {"SKILL.md": "x"})
    put(a, "partial", {"SKILL.md": "x"})
    text = ssc.render(ssc.analyse({"a": a, "b": b}, canon))
    assert text.index("unreachable") < text.index("some profiles only")
