# Memory Index

> **This is the canonical entry point.** Always read this file first; it links out to everything else.
> Update this index whenever you add, rename, or remove a memory file.

## Top-level identity

- [user.md](user.md) — Who you are, your goals, your setup, the bigger-picture motivation *(bootstrap required)*
- [soul.md](soul.md) — How Claude talks to you — tone, format, vocabulary, what to avoid *(bootstrap required)*
- [sol.md](sol.md) — Your Claude instance identity and name *(optional — delete if you don't want this)*
- [frame.md](frame.md) — The shared philosophical/operational framework *(optional)*
- [goals.md](goals.md) — Your current goals, assessed weekly by the Goal Loop *(optional — the loop stays off until you fill it in; see docs/goal-loop.md)*

## Behavioral rules — `feedback/`

- [feedback/BOOTSTRAP.md](feedback/BOOTSTRAP.md) — How to write rules; your first-3-rules prompt
- [feedback/never_commit_without_permission.md](feedback/never_commit_without_permission.md) — Default commit policy (universal; override per project)

> Add more rules here as you accumulate them. Use `/session-reflect` to capture them at session end.

## Active projects — `projects/`

- [projects/README.md](projects/README.md) — Format guide + bootstrap prompt

> Add one file per active project. Keep these current — stale project briefs mislead Claude.

## Ideas — `ideas/`

- [ideas/README.md](ideas/README.md) — Format guide; capture liberally, graduate selectively

## Archive — `archive/`

Files that are no longer active but kept for history. Don't delete — just move here when superseded.

---

## When in doubt

Write identity-level facts (who you are, standing rules, project context) to this `memory/` directory — not to the Claude Code harness's per-project auto-memory. The harness's memory is per-directory; this system is global. See `CLAUDE.md` for the routing rule.
