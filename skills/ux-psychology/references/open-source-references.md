# Open-source repos cataloging UX psychology, cognitive biases, dark patterns

> Research digest behind `SKILL.md`, produced by one sub-agent of a six-way parallel research pass (each agent had one lane; "Agent A" through "Agent F" below refer to those lanes). Claims carry the agent's own confidence flags; verify a load-bearing one against its cited source before relying on it.


Sub-question F of 6-agent swarm enriching the ux-psychology skill. Scope: structured open-source references (repos, cheat sheets, taxonomies) — NOT Laws of UX content itself (Agent A), NOT Cialdini (Agent B), NOT habit models (Agent C), NOT other YouTube creators (Agent D), NOT dark pattern taxonomy detail (Agent E, though repo pointers overlap and are noted here for completeness).

---

## 1. Buster Benson's Cognitive Bias Cheat Sheet — the organizing scheme

**Confidence: HIGH (fetched and verified JSON structure directly)**

- Original essay: https://buster.medium.com/cognitive-bias-cheat-sheet-55a472476b18 (Medium, "Better Humans")
- Canonical data mirror: https://github.com/busterbenson/public/blob/master/cognitive-bias-cheat-sheet.json — this is Buster Benson's own public GitHub, containing the source JSON for the cheat sheet.
- Verified structure: the JSON has **4 top-level categories**, each with nested subcategories, bottoming out in ~175-180 individual biases:
  1. **"Too Much Information"** — noticing primed/stored memories, distinctive/changed things, confirming existing beliefs, noticing flaws in others.
  2. **"Not Enough Meaning"** — finding patterns in sparse data, filling in gaps with stereotypes/generalities, favoring familiar/liked things, simplifying probabilities/numbers.
  3. **"Need To Act Fast"** — need to be confident enough to act, need to act/react quickly, need to complete things we've invested in, need to preserve autonomy/status/others' feelings, need to choose the option that appears simplest.
  4. **"What Should We Remember?"** — editing/reinforcing memories after the fact, discarding specifics for generalities, reducing events/lists to key elements, storing memories differently by how they were experienced.
- **Verdict: genuinely useful organizing structure.** This 4-bucket "why does this bias exist" framing (info overload / meaning-making / speed / memory) is a clean, memorable taxonomy that could organize a cognitive-bias section of the skill far better than an alphabetical or ad-hoc list. Recommend citing this scheme directly rather than the derivative visualizations.

Secondary mirrors/visualizations of the same data (lower value — derivative, not more authoritative than the source JSON):
- https://github.com/scottleedavis/cognitive-bias-codex — D3.js interactive chart + `bias.csv`, drills into the 200+ biases hierarchically. 10 stars, 3 forks, ~21 commits, essentially dormant. HIGH confidence (fetched) that it's a visualization tool, not additional taxonomy — doesn't clearly confirm it reproduces Benson's 4-bucket labels verbatim, just cites the same source material.
- https://gist.github.com/hectorm/38fb03ea8ca1d4c1baee400d7f5efaad — gist mirror of the codex image/data. LOW confidence, not fetched, likely just a static asset re-host.
- https://gist.github.com/tmsss/8cab5a0c39c2435ae1be990226492936 — another gist mirror. LOW confidence, not fetched.

Verdict on this cluster: **link the primary source (busterbenson/public JSON) and use the 4-category scheme as an organizing device.** The D3/codex forks add a browsable visualization but no new intellectual content.

---

## 2. Laws of UX references

**Confidence: MED** (searched, partially fetched via search snippets, not deep-fetched — Agent A owns Laws of UX content itself, so kept this brief)

- https://lawsofux.com/ — the official site (not a GitHub repo; Jon Yablonski's canonical reference). Should already be Agent A's core citation.
- https://github.com/dotdwebo/learning-ux — small personal study repo, low effort, not a durable reference.
- https://github.com/RobsonVinicius/UX-Design — Portuguese-language personal study notes repo referencing Laws of UX; low effort.
- Verdict: no standalone GitHub repo meaningfully improves on lawsofux.com itself for this category. Not worth citing beyond the official site (Agent A's lane).

---

## 3. Dark pattern taxonomies / code repos

**Confidence: HIGH (fetched)** — flagged here because Agent E owns full taxonomy detail; these are the structured/code artifacts specifically.

- **aruneshmathur/dark-patterns** — https://github.com/aruneshmathur/dark-patterns — 138 stars, 22 forks. Contains the code + data from the CSCW 2019 paper "Dark Patterns at Scale: Findings from a Crawl of 11K Shopping Websites" (OpenWPM-based crawler, clustering analysis, dataset of dark patterns found across 11K e-commerce sites). This is a **research dataset + detection code**, not a curated reading list — genuinely the most-cited empirical dark-patterns corpus in academia. Useful as a primary-source citation for "how prevalent are dark patterns" claims.
- **SageSELab/AidUI** — https://github.com/SageSELab/AidUI — 26 stars, 11 forks. ICSE 2023 paper replication package. Contains a **unified taxonomy merging Gray et al., Mathur et al., and Brignull et al. schemes into 7 parent categories / 27 dark-pattern classes**, PLUS an actual detection pipeline (deep-learning visual cue detection → UI/text content extraction → pattern matching → DP prediction) and the CONTEXTDP evaluation dataset (162 web + 339 mobile screenshots, 301 labeled DP instances). **Flag: this is a genuine research CODE artifact** (Python/Jupyter), not just a list — most rigorous unified taxonomy found. Worth flagging to Agent E as the best "meta-taxonomy that reconciles the 3 major competing dark-pattern classification schemes."
- Also surfaced but not deep-fetched (LOW confidence): `yamanalab/ec-darkpattern` (ML dataset for e-commerce dark pattern text detection), `NicholasTung/dark-patterns-recognition` (small hackathon Chrome extension), `oneuxco/dark-patterns-plugin` (browser plugin). All niche/lower-value versus the two above.

---

## 4. Component/code libraries implementing psychological UX patterns (flagged per instructions)

**Confidence: HIGH on classification, MED on completeness of feature claims**

None of the repos found are a React/Vue **component kit** that implements psychological patterns as ready-to-use widgets (e.g., a "social proof widget library" or "smart defaults" component pack) — that specific genre did not surface in searches. What DID surface, closer to "actionable code" than "reading list":

- **Nuclear-Marmalade/ux-psychology-skill** — https://github.com/Nuclear-Marmalade/ux-psychology-skill — 16 stars, 3 forks, MIT, active (v1.1.0 release dated Apr 2026). **This is a directly competing/adjacent Claude Code skill** (same genre as this skill): a SKILL.md + `knowledge/` directory of **65 behavioral psychology principles across 11 categories** (Attention, Gestalt, Memory, Sensemaking, Decision Making, Motor/Interaction, Motivation, Cognitive Biases, Persuasion, Emotion, Ethics), plus `patterns/` (conversion-flow templates) and `examples/` (real review cases: SaaS landing pages, e-commerce checkout, subscriptions). It explicitly documents dark-pattern manipulation techniques as **prohibited** patterns rather than implementing them. **High-value structural reference** — worth comparing this skill's category taxonomy against its 11 categories for gaps, and possibly citing/crediting as prior art if this skill converges on similar structure.
- **phazurlabs/ux-ui-mastery** — https://github.com/phazurlabs/ux-ui-mastery — 26 stars, 9 forks, MIT, v3.0.0, actively developed (open PRs/issues). A much larger Claude Code **plugin** (310K+ words, 19 skill domains, 55 reference docs, 10 commands) covering 25+ Laws of UX with formulas, 50+ cognitive biases with ethical/dark-pattern annotations, plus implementation skills (React/SwiftUI/CSS components, Figma workflows, WCAG 2.2/3.0, motion design, agentic-AI/spatial/voice UX). This is the broadest and most actively maintained of anything found in this search — **closest thing to a "competing productized version" of this skill**, worth a structural skim for coverage gaps even though it's a full plugin rather than a single skill file.
- No true "psychological pattern component library" (e.g. a button/modal kit implementing scarcity timers, social-proof toasts, default-nudges as installable UI components) was found in this pass.

---

## Digest of Verdicts

| Resource | Type | Verdict |
|---|---|---|
| busterbenson/public JSON | primary source data | Cite directly; use 4-category scheme as organizing structure |
| scottleedavis/cognitive-bias-codex | D3 visualization | Nice-to-link, not essential; dormant |
| aruneshmathur/dark-patterns | research dataset+code | Cite as empirical prevalence source |
| SageSELab/AidUI | unified taxonomy + detection code | Best reconciled 7-category/27-class taxonomy; flag to Agent E |
| Nuclear-Marmalade/ux-psychology-skill | competing Claude skill | High-value structural comparison (11 categories, 65 principles) |
| phazurlabs/ux-ui-mastery | competing Claude plugin | Broadest competing reference; skim for gaps |
| awesomelistsio/awesome-ux, other "awesome-ux" repos | curated link lists | Low-effort, generic; skip |
| lawsofux.com + small personal repos | Laws of UX | Official site sufficient; repos add nothing |
