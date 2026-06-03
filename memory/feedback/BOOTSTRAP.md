# Feedback Rules — How to Write Them

This folder holds standing behavioral rules — corrections, confirmations, and patterns that Claude should apply everywhere, forever.

## When to create a feedback rule

- Claude did something wrong that you had to correct ("no, don't do that")
- Claude did something right in a non-obvious way and you confirmed it ("yes, exactly that")
- A pattern repeated across sessions that you want permanently encoded
- A format, style, or approach you've explicitly rejected

## File format

```markdown
---
name: rule-slug-in-kebab-case
description: One-line summary — used to decide relevance. Be specific.
type: feedback
---

# Rule Title

[The rule itself, stated plainly in 1–3 sentences]

**Why:** [The reason — often a specific incident, date, or strong preference]

**How to apply:** [When/where this rule kicks in; how to judge edge cases]

## Cross-references
- [[related-rule]]
```

## Bootstrap: write your first 3 rules

Answer these to seed your feedback folder:

1. **What's the #1 thing Claude does by default that you hate?**
   → Write a rule preventing it.

2. **What's a past incident where Claude's output was wrong in a costly way?**
   → Write a rule preventing the root cause.

3. **What's your non-negotiable commit/deploy/push policy?**
   → Write a rule for it. (The default in this repo: never commit without explicit permission.)

## Examples in this folder

- `never_commit_without_permission.md` — the one rule that comes pre-loaded (everyone needs it)
