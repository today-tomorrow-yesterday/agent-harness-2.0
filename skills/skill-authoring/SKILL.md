---
name: skill-authoring
description: "Author or repair a skill so it is actually invokable, not an essay that silently never loads — the directory + SKILL.md + BOM-free frontmatter contract, and the guard and test that will reject a malformed one. Triggers on: into a skill, make this a skill, create a skill, as a skill"
---

# Authoring a skill that can actually be invoked

The failure this exists to prevent: asked to "convert this into a skill," an agent produced a
well-written 51-line markdown essay with no frontmatter, under a filename nothing looks for, in a
directory nothing scans. It read like a skill and was inert. Reviewing for it found a second one
**already shipped in this repo**, unloadable because a UTF-8 BOM sat ahead of its `---`.

**Both failures are silent.** Nothing errors. No warning appears. The skill simply never loads,
and you find out weeks later when invoking it does nothing.

## The contract

A skill is a **directory**, not a file:

```
skills/<skill-name>/SKILL.md
```

`SKILL.md` must open with these as its **very first bytes** — no BOM, no title above it:

```markdown
---
name: <skill-name>          # MUST equal the directory name
description: <what it does, and when to use it>
---
```

## Writing the description

It is not decoration — it is the text a harness matches on to decide whether to load the skill at
all. A vague description produces a skill that exists and never fires. Say **what it does** and
**when to use it**, and name the situation concretely enough that a reader can tell whether they
are in it.

If your setup derives trigger vocabulary from descriptions, declare it explicitly rather than
hoping it gets inferred from prose:

```
description: ... Triggers on: into a skill, make this a skill, create a skill
```

Keep trigger phrases short — three or four words. Long phrases match nothing, because a real
person's wording will differ by a word or two and never line up.

## Two layers will judge this

| Layer | Catches | Where |
|---|---|---|
| **Guard** (write time) | loose `.md`, missing or BOM'd frontmatter, name ≠ directory | `bin/hooks/skill-shape-guard.py` |
| **Test** (drift) | anything already on disk that cannot be invoked | `bin/tests/test_skill_conformance.py` |

Both read one shared policy: `bin/skill_policy.py`. Register the guard once with:

```
python bin/register_hook.py skill-shape-guard
```

To see the contract at any time, including the roots currently governed:

```
python bin/skill_policy.py
```

## Checklist

- [ ] Directory named for the skill; `SKILL.md` inside it
- [ ] `---` is the **first byte** of the file — no BOM, no heading above it
- [ ] `name:` exactly matches the directory name
- [ ] `description:` says what it does **and** when to use it
- [ ] `python bin/skill_policy.py` reports no problems
- [ ] `python -m pytest bin/tests/test_skill_conformance.py -q` passes

## Deliberate exceptions

A markdown file in a skills root that is genuinely *not* an invokable skill — an operator runbook,
a catalog — is allowed two ways: prefix it with `_`, or register it in
`skill_policy.DOCUMENTED_FLAT_FILES` **with a reason**. Exceptions are cheap but never free: a
guard that flags legitimate files is one people learn to switch off, and a switched-off guard
protects nothing.

## Writing a skill for other people

Keep it free of anything local — absolute paths, machine names, private project names, one
team's internal tooling. Grep your draft for drive letters and home directories before handing it
over. Paths inside the skill should be relative to the repo, the way everything else here is.
