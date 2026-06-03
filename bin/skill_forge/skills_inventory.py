"""Enumerate skills from their SKILL.md frontmatter."""
from __future__ import annotations
import re
from pathlib import Path

_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _parse_frontmatter(text: str) -> dict[str, str]:
    m = _FM_RE.match(text)
    if not m:
        return {}
    out: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith((" ", "\t", "-")):
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def list_skills(skills_dir: Path) -> list[dict]:
    """Return [{name, description, origin, path}] for each <skill>/SKILL.md.

    origin: 'skill-forge' if the frontmatter declares it, else 'authored'.
    """
    skills_dir = Path(skills_dir)
    if not skills_dir.exists():
        return []
    out: list[dict] = []
    for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
        try:
            fm = _parse_frontmatter(skill_md.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        name = fm.get("name") or skill_md.parent.name
        out.append({
            "name": name,
            "description": fm.get("description", ""),
            "origin": "skill-forge" if fm.get("origin") == "skill-forge" else "authored",
            "path": str(skill_md),
        })
    return out
