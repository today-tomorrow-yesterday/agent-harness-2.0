"""memory-index-split.py: shrink the memory index without losing a single line.

The one property that matters is conservation: every line of the original lands in exactly one
output, and the script refuses to write — or restores the backup — if that does not hold.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

BIN = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("memory_index_split",
                                              str(BIN / "memory-index-split.py"))
mis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mis)

INDEX = """# Memory Index

> Always read this file first.

## Top-level identity

- [user.md](user.md) — who you are
- [soul.md](soul.md) — how to talk

## Behavioral rules — `feedback/`

- [feedback/never_commit.md](feedback/never_commit.md) — commit policy
- [feedback/tests_first.md](feedback/tests_first.md) — write the test first
- external: [docs](https://example.com/docs) and [anchor](#top)

```
## not a heading, inside a fence
```

## Custom Things

- [projects/alpha.md](projects/alpha.md) — the alpha project
"""


def write_index(tmp_path: Path, text: str = INDEX) -> Path:
    mem = tmp_path / "memory"
    mem.mkdir()
    (mem / "MEMORY.md").write_text(text, encoding="utf-8")
    return mem


def test_split_routes_each_section_and_counts_entries():
    router, files, stats = mis.split(INDEX)
    assert set(files) == {"top-level.md", "feedback.md", "custom-things.md"}
    assert "[Top-level identity](_index/top-level.md)" in router
    assert "· 2 entries" in router
    assert [s[2] for s in stats] == [2, 3, 1]


def test_fenced_heading_is_not_a_section():
    _router, files, _ = mis.split(INDEX)
    assert "## not a heading, inside a fence" in files["feedback.md"]


def test_relative_links_gain_one_level_external_and_anchor_links_do_not():
    _router, files, _ = mis.split(INDEX)
    fb = files["feedback.md"]
    assert "](../feedback/never_commit.md)" in fb
    assert "](https://example.com/docs)" in fb
    assert "](#top)" in fb


def test_every_bullet_survives_the_split():
    router, files, _ = mis.split(INDEX)
    assert mis.bullets_missing(INDEX, router, files) == []


def test_bullets_missing_detects_a_lost_line():
    router, files, _ = mis.split(INDEX)
    files["custom-things.md"] = "# Custom Things\n"
    assert mis.bullets_missing(INDEX, router, files) == [
        "- [projects/alpha.md](projects/alpha.md) — the alpha project"]


def test_two_headings_routed_to_one_file_do_not_overwrite_each_other():
    text = "# I\n\n## Feedback A\n\n- a\n\n## Behavioral rules\n\n- b\n"
    _router, files, _ = mis.split(text)
    assert set(files) == {"feedback.md", "feedback-2.md"}


def test_dry_run_writes_nothing(tmp_path):
    mem = write_index(tmp_path)
    assert mis.main(["--memory-dir", str(mem)]) == 0
    assert (mem / "MEMORY.md").read_text(encoding="utf-8") == INDEX
    assert not (mem / "_index").exists()


def test_apply_writes_router_sections_and_backup(tmp_path):
    mem = write_index(tmp_path)
    assert mis.main(["--memory-dir", str(mem), "--apply"]) == 0
    assert (mem / "MEMORY.md.bak-presplit").read_text(encoding="utf-8") == INDEX
    assert mis.is_router((mem / "MEMORY.md").read_text(encoding="utf-8"))
    assert (mem / "_index" / "feedback.md").is_file()
    raw = (mem / "_index" / "feedback.md").read_bytes()
    assert b"\r\n" not in raw and not raw.startswith(b"\xef\xbb\xbf")


def test_second_apply_refuses_to_shred_the_router(tmp_path):
    mem = write_index(tmp_path)
    mis.main(["--memory-dir", str(mem), "--apply"])
    router = (mem / "MEMORY.md").read_text(encoding="utf-8")
    assert mis.main(["--memory-dir", str(mem), "--apply"]) == 0
    assert (mem / "MEMORY.md").read_text(encoding="utf-8") == router


def test_post_write_loss_restores_the_backup(tmp_path, monkeypatch):
    mem = write_index(tmp_path)
    monkeypatch.setattr(mis, "bullets_missing", lambda *a: ["- lost"])
    assert mis.main(["--memory-dir", str(mem), "--apply"]) == 1
    assert (mem / "MEMORY.md").read_text(encoding="utf-8") == INDEX
    assert not any((mem / "_index").glob("*.md"))


def test_missing_index_is_reported(tmp_path):
    assert mis.main(["--memory-dir", str(tmp_path)]) == 2


def test_the_shipped_memory_index_splits_losslessly():
    shipped = BIN.parent / "memory" / "MEMORY.md"
    text = shipped.read_text(encoding="utf-8")
    router, files, _ = mis.split(text)
    assert mis.bullets_missing(text, router, files) == []
