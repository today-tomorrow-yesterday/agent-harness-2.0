# Skills: when to use each one

One line per skill in `skills/`. Details, prerequisites and the maintenance programs are in
[`skills/_index.md`](../skills/_index.md); each skill's own `SKILL.md` is the full method.

- **`fable-discipline`** — on any non-trivial engineering or analysis task, before handing a conclusion to someone who will act on it, and whenever you brief a subagent (inject its `references/worker-digest.md`).
- **`git-verified-agent-orchestration`** — when delegating a multi-step build to subagents and you need each step proven by a real, reviewed commit rather than the agent's own report.
- **`research-swarm`** — when a question has several distinct angles and the answer feeds a decision; use its `quick` mode when only one angle is real.
- **`repo-vet`** — before installing or running any external repo or tool someone wants to use.
- **`repo-steal`** — when the goal is to learn from an external repo (or a field of them) and graft its best mechanisms into your own system, without running it.
- **`skill-authoring`** — whenever you create, convert, or repair a skill, so it actually loads.
- **`sync-agent-tools`** — after adding or editing a skill or MCP server that every Claude profile (or Codex / Gemini seat) should have, or when two sessions behave differently for no visible reason.
- **`session-reflect`** — at the end of a session that contained corrections or newly confirmed ways of working, to turn them into durable memory.
- **`onboard`** — once, when setting this harness up on a new machine.
- **`visual-explainer`** — when someone needs to understand something structural (a schema, a data flow, two or three design options, a before/after) and a prose doc would not land.
- **`ux-psychology`** — when designing or critiquing an onboarding flow, paywall, pricing page or sign-up form, or when a screen looks fine but does not convert.
- **`page-clone`** — when you need a whole web page captured (screenshot, offline clone, rendered DOM) as a visual spec or for a teardown.
- **`domain-check`** — when looking for an available domain name or comparing TLD prices.
- **`domain-register`** — when buying a domain.
- **`domain-dns-setup`** — when pointing a domain at a server, CDN or host.
- **`domain-email-setup`** — when configuring a domain's mail records (MX, SPF, DKIM, DMARC).
- **`domain-full-setup`** — when launching a new project that needs a domain, DNS and email from scratch.
