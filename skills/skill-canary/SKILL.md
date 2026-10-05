---
name: skill-canary
description: Canary-before-promote gate for skills. Snapshots the Claude profile's current copy of a skill, smoke-tests the repo copy (SKILL.md is invokable, helper scripts compile), logs a CanaryStatus record to forge/evolution.jsonl, and only promotes on Pass — with one-command rollback. Use before pushing an edited skill live, or when asked to "canary this skill", "gate the skill edit", "check all skills" or "roll back that skill".
---

# skill-canary — validate a skill edit before it goes live

A skill edited in this repo (`skills/<name>/`) reaches your Claude profile's skills dir
by being copied there. Without a gate that copy happens with no validation and no
rollback, and a broken skill fails *silently*: a malformed frontmatter block or a
syntax-broken helper script never errors, the skill just stops loading.

`bin/skill_canary.py` puts a snapshot -> smoke-test -> promote-or-rollback gate in front
of that copy.

## Run it

```bash
python bin/skill_canary.py <skill>              # snapshot + smoke-test + log (gate only)
python bin/skill_canary.py --promote <skill>    # gate, and on Pass copy repo -> profile
python bin/skill_canary.py --rollback <skill>   # restore the latest snapshot
python bin/skill_canary.py --list <skill>       # list snapshots for a skill
python bin/skill_canary.py --check-all          # smoke-test every repo skill, write nothing
```

Exit codes: `0` = Passed (safe to promote), `1` = Failed (profile untouched),
`2` = usage error / skill not found.

The profile is `$CLAUDE_CONFIG_DIR/skills` if that variable is set, otherwise
`~/.claude/skills`. Pass `--profile DIR` (repeatable) to gate more than one profile.

## What the gate does

1. **Snapshot** — before any overwrite, copies the profile's current copy of the skill to
   `forge/skill-versions/<skill>/<utc-fingerprint>/` plus a `_manifest.json` recording
   which profiles had it. This is what `--rollback` restores.
2. **Smoke-test the repo copy**:
   - `SKILL.md` passes `bin/skill_policy.py` — frontmatter opens the file, `name` and
     `description` present, `name` matches the directory, no byte-order mark;
   - every co-located or referenced helper `.py` compiles.
3. **Log** — appends a CanaryStatus record to `forge/evolution.jsonl`:
   `{"strategy":"canary","canary":"Passed|Failed","checks":[...],"crash":{...}|null,"snapshot":"..."}`.
4. **Promote or hold** — on Passed exit 0 (with `--promote`, also copy the skill into the
   profile). On Failed exit non-zero and leave the profile untouched.

## Use it as the gate in front of any copy step

```bash
python bin/skill_canary.py my-skill && <your copy / sync step>
```

The `&&` is the gate: the copy only runs if the canary passed.

## Limits

- The smoke-test is a structure/syntax gate, not a behavioral test. It catches the
  failures that silently break a live skill, not logic bugs.
- `--rollback` restores the **latest** snapshot. Older ones are listed by `--list` and
  can be copied back by hand from `forge/skill-versions/`.
- `bin/release_gate.py` runs `--check-all` as one of its checks.
