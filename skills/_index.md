# Skills index

Every skill in `skills/`, what it is for, and what it needs. A skill is a directory with a
`SKILL.md` (see `skill-authoring`); files starting with `_`, like this one, are support files,
not skills. One-line "when to use" guidance for each lives in [`docs/skills.md`](../docs/skills.md).

Install skills into a Claude profile by copying the directory into `<config-dir>/skills/`, or keep
every profile identical with `sync-agent-tools`.

## Engineering and agent practice

| Skill | What it does | Needs |
|---|---|---|
| `fable-discipline` | Decision-point artifacts (INTENT / AUTH / TWINS / PENDING), the VERIFIED / INFERRED / ASSUMED claim contract, a 5-question pre-ship self-test, and loadable protocols for attacking your own conclusion, risk budgets, failure tells and briefing subagents. `references/worker-digest.md` is the contract other skills inject into worker prompts. | — |
| `git-verified-agent-orchestration` | Delegate to subagents where every unit of work is a real git commit, independently verified and separately reviewed before the next starts. | git |
| `research-swarm` | Parallel deep research: decompose, dispatch background agents, dedupe sources with `source-ledger.py`, spot-verify load-bearing claims, synthesize one cited, confidence-flagged report with coverage gaps. | web search/fetch tools; Python for the ledger |
| `repo-vet` | Clear an external repo for actually running it: quarantine clone, authenticity check, static vet, six-lens adversarial audit, fitness check, hardened setup, verdict. | git |
| `repo-steal` | Mine an external repo for transferable patterns, produce a categorized steal-list scored against your system, verify you do not already have it, graft the good parts. | git |
| `skill-authoring` | Author or repair a skill so it actually loads: directory + `SKILL.md` + BOM-free frontmatter, and the guard and test that enforce it. | — |
| `sync-agent-tools` | One manifest (`config/agent-tools.example.yaml`) keeps MCP servers, skills and a shared instructions file identical across Claude profiles and Codex / Gemini seats; `bin/skill-sync-check.py` reports drift read-only. | Python, PyYAML, `claude` CLI |
| `session-reflect` | Scan the current session for corrections and confirmed approaches and draft memory entries for approval. | the claude-brain database |
| `onboard` | First-time setup of this harness on a new machine, including the memory interview. | Python |

## Design and communication

| Skill | What it does | Needs |
|---|---|---|
| `visual-explainer` | Build a self-contained, dark-first HTML explainer (numbered steps, real data with one highlighted row, option cards, verdict tables) instead of a prose doc when someone must understand something structural. Ships `template.html`. | a browser |
| `ux-psychology` | Critique or design conversion flows (onboarding, paywalls, pricing, sign-up) from named behavioral mechanisms, and flag when a technique becomes a dark pattern. | — |
| `page-clone` | Capture a web page as a full-page screenshot, a self-contained `.mhtml` clone and its rendered DOM, for teardown or rebuild. Ships `page-clone.mjs`. | Node 18+, `npm install` in the skill dir, Chrome / Edge or Playwright Chromium |

## Domains (all need the open-source `domain-suite-mcp` server)

| Skill | What it does |
|---|---|
| `domain-check` | Availability and pricing across TLDs. |
| `domain-register` | Register a domain. |
| `domain-dns-setup` | A / CNAME / TXT records. |
| `domain-email-setup` | MX, SPF, DKIM, DMARC for a mail provider. |
| `domain-full-setup` | Check → register → DNS → email, end to end. |

## Maintenance programs that pair with these skills

| Program | Purpose |
|---|---|
| `bin/sync-agent-tools.py` | Apply the agent-tools manifest to every seat (gated: every skill must validate first). |
| `bin/skill-sync-check.py` | Read-only drift report across profiles and against `skills/`. |
| `bin/skill_deps.py` | Flag skills whose declared `knowledge:` documents changed after `knowledge_synced:`. |
| `bin/memory-index-split.py` | Split an oversized `memory/MEMORY.md` into a small router + verbatim section files, losslessly. |
| `bin/memory-garden.py` | Classify claude-brain facts by time-decayed confidence (report only, never deletes); optional knowledge-graph edge pass. |
