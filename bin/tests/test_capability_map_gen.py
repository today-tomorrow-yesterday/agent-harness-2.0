"""Tests for bin/capability-map-gen.py -- the generated skill-discovery map.

Two defects this guards, both found in the original generator:

1. NON-DETERMINISM. Ranking sorted a `set` with ties on (has-space, -len), so which tied phrase
   survived MAX_PER_SKILL depended on set iteration order, which varies per process because Python
   randomizes string hashing. A generated file that churns without an input change makes its diffs
   meaningless. Only subprocesses under different PYTHONHASHSEED values can exercise it -- within
   one process set order is stable and the bug is invisible.

2. PROSE FRAGMENTS used as triggers. Slicing a description at punctuation produced entries like
   `deploying) that the queue`. Nobody types those; they occupied capped slots real words wanted.

Plus: the committed map must match skills/ (it is generated, so staleness is a bug).
"""
from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

BIN = Path(__file__).resolve().parents[1]
GEN = BIN / "capability-map-gen.py"


def _load():
    spec = importlib.util.spec_from_file_location("capability_map_gen", GEN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


g = _load()


def _skill(root: Path, name: str, description: str) -> None:
    (root / name).mkdir(parents=True)
    (root / name / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n", encoding="utf-8")


# ------------------------------------------------------------------ freshness -----------------

def test_committed_map_matches_the_skills_in_this_repo():
    r = subprocess.run([sys.executable, str(GEN), "--check"], capture_output=True, text=True,
                       timeout=120, env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    assert r.returncode == 0, (r.stdout + r.stderr +
                               "\nRegenerate with: python bin/capability-map-gen.py --write")


def test_committed_map_imports_and_every_pattern_compiles():
    mod = g.load_module()
    assert mod.GENERATED_CAPABILITY_MAP
    for entry_id, skills, pat, msg in mod.GENERATED_CAPABILITY_MAP:
        re.compile(pat, re.IGNORECASE)
        assert msg.strip() and skills and entry_id


# ------------------------------------------------------------------ determinism ---------------

def _report(seed: str) -> str:
    env = dict(os.environ, PYTHONHASHSEED=seed, PYTHONIOENCODING="utf-8")
    p = subprocess.run([sys.executable, str(GEN)], capture_output=True, text=True, env=env,
                       timeout=120, errors="replace")
    assert p.returncode == 0, p.stderr[-400:]
    return p.stdout


@pytest.mark.parametrize("seed_a,seed_b", [("0", "1"), ("1", "12345")])
def test_output_is_identical_across_hash_seeds(seed_a, seed_b):
    assert _report(seed_a) == _report(seed_b)


def test_tied_phrases_rank_alphabetically():
    tied = {"harden", "animate", "distill", "clarify"}
    assert sorted(tied, key=g.rank_key) == ["animate", "clarify", "distill", "harden"]


def test_cap_keeps_the_same_phrases_regardless_of_input_order(tmp_path):
    root = tmp_path / "skills"
    _skill(root, "polish-kit", "Use when: zeta, alpha, gamma, delta, beta, epsilon, theta, kappa")
    a = g.build([root])["entries"][0]["triggers"]
    b = g.build([root])["entries"][0]["triggers"]
    assert a == b and len(a) == g.MAX_PER_SKILL


# ------------------------------------------------------------------ fragments -----------------

@pytest.mark.parametrize("frag", [
    "deploying) that the queue", "transcript dna (hook structure",
    "toggle <handle> [cadence", 'a "quoted" piece', "-leading hyphen", "trailing hyphen-",
])
def test_prose_fragments_are_rejected(frag):
    assert g.FRAGMENT.search(frag)


@pytest.mark.parametrize("good", [
    "into a skill", "make this a skill", "orchestrate subagents", "safety review", "first-time setup",
])
def test_real_triggers_are_not_rejected(good):
    assert not g.FRAGMENT.search(good)


def test_phrases_drops_fragments_end_to_end():
    out = g.phrases("demo", "Use when: deploying) that the queue, into a skill, paywall")
    assert "into a skill" in out and "paywall" in out
    assert not [p for p in out if ")" in p]


def test_over_four_word_phrases_are_dropped():
    out = g.phrases("demo", "Use when: convert this into a skill please")
    assert not [p for p in out if len(p.split()) > 4]


def test_name_tokens_consume_cap_slots():
    out = g.phrases("skill-authoring", "")
    assert "skill authoring" in out and "authoring" in out


# ------------------------------------------------------------------ pruning -------------------

def test_short_name_fragments_are_pruned_but_full_name_and_long_fragments_stay():
    skills = [{"name": "safety-review", "description": "Review and clear the queue."},
              {"name": "skill-authoring", "description": "Author a skill."},
              {"name": "domain-register", "description": "Register a domain."},
              {"name": "watch", "description": "Watch a video."}]
    per = {sk["name"]: g.phrases(sk["name"], sk["description"]) for sk in skills}
    g.prune_generic(per, skills)
    assert "safety review" in per["safety-review"]
    assert "review" not in per["safety-review"] and "safety" not in per["safety-review"]
    assert "register" not in per["domain-register"]
    assert "authoring" in per["skill-authoring"]
    assert "watch" in per["watch"]                      # a single-word name is its own trigger


def test_shared_vocabulary_single_words_are_pruned():
    skills = [{"name": f"tool-{i}", "description": "Use when: publishing"} for i in range(3)]
    per = {sk["name"]: g.phrases(sk["name"], sk["description"]) for sk in skills}
    dropped = g.prune_generic(per, skills)
    assert all("publishing" not in ps for ps in per.values())
    assert any(ph == "publishing" and n >= 3 for _, ph, n in dropped)


def test_contested_phrase_becomes_one_menu_entry(tmp_path):
    root = tmp_path / "skills"
    _skill(root, "banner-maker", "Use when: hero banner")
    _skill(root, "ad-designer", "Use when: hero banner")
    entries = g.build([root])["entries"]
    menu = [e for e in entries if e["id"] == "ad-designer+banner-maker"]
    assert menu and "hero banner" in menu[0]["triggers"]
    assert "/ad-designer" in menu[0]["message"] and "/banner-maker" in menu[0]["message"]


# ------------------------------------------------------------------ the live map --------------

def test_live_map_is_quiet_on_ordinary_sentences_and_hits_declared_triggers():
    mod = g.load_module()

    def hits(txt):
        return [msg.split(" ")[0] for _i, _s, pat, msg in mod.GENERATED_CAPABILITY_MAP
                if re.search(pat, txt, re.I)]

    assert hits("review our nightly runs") == []
    assert hits("this session went well") == []
    assert hits("how do I register this hook?") == []
    assert "/skill-authoring" in hits("convert this into a skill")
    assert "/safety-review" in hits("what is in the safety queue")


def test_cap_is_reported_not_silent():
    src = GEN.read_text(encoding="utf-8")
    assert "[capped]" in src and "DROPPED" in src
