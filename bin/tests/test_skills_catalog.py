"""Every skill on disk is listed in both catalogs, and every catalog entry is a real skill.

A skill missing from the catalog is a skill nobody knows to reach for; a catalog entry with no
skill behind it sends people to something that does not exist. Both drift silently.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKILLS = REPO / "skills"
CATALOGS = (SKILLS / "_index.md", REPO / "docs" / "skills.md")


def on_disk() -> set[str]:
    return {p.name for p in SKILLS.iterdir()
            if p.is_dir() and not p.name.startswith((".", "_")) and (p / "SKILL.md").is_file()}


def listed(catalog: Path) -> set[str]:
    text = catalog.read_text(encoding="utf-8")
    names = set(re.findall(r"^\|\s*`([a-z0-9-]+)`\s*\|", text, re.M))
    names |= set(re.findall(r"^- \*\*`([a-z0-9-]+)`\*\*", text, re.M))
    return names


def test_every_skill_is_catalogued():
    for catalog in CATALOGS:
        missing = sorted(on_disk() - listed(catalog))
        assert not missing, f"{catalog.relative_to(REPO)} does not list: {missing}"


def test_every_catalogued_skill_exists():
    for catalog in CATALOGS:
        ghosts = sorted(listed(catalog) - on_disk())
        assert not ghosts, f"{catalog.relative_to(REPO)} lists skills that do not exist: {ghosts}"
