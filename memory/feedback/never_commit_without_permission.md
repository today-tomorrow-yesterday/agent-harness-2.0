---
name: never_commit_without_permission
description: Never run git commit, push, add, or any version-control mutation without explicit user permission in the current session.
type: feedback
---

# Never Commit Without Permission

Never run `git commit`, `git push`, `git add`, or any other version-control mutation unless explicitly asked **in the current session**.

- "Done" does not mean commit.
- Finishing a task does not mean commit.
- A prior session's "next step" is not standing authorization.
- Read-only git (status / log / diff / fetch / branch / checkout) is fine.
- When in doubt, ask: *"Want me to commit this?"* and wait for an explicit yes.

**Why:** This rule prevents lost work and unintended history. Applied universally until a project explicitly opts out.

**How to apply:** Per-project overrides are acceptable (e.g., a project with auto-commit hooks). When a project overrides this, note it in its project brief. The default is always: ask first.
