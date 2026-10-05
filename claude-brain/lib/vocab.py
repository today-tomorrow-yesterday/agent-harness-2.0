"""Your tag vocabulary — the canonical TAG_KEYWORDS dict.

Used by `hooks/session-end.py` for live session tagging, and by
`scripts/import_*.py` + `scripts/brain_tag_review.py` for batch/CLI
operations. Single source of truth so the dict can't drift across files.

Everything below is an EXAMPLE. Replace the keys and keywords with the projects,
tools and topics you actually work on — a tag is only useful if its keywords
show up in your own sessions.
"""

from __future__ import annotations


TAG_KEYWORDS: dict[str, list[str]] = {
    # EXAMPLE projects — replace these keys + keywords with your own.
    "webapp":            ["webapp", "web app", "frontend", "backend", "api"],
    "research":          ["research", "literature review", "experiment", "notes"],
    "content":           ["content", "article", "draft", "publishing"],

    # Agent infrastructure
    "harness":           ["agent-harness", "memory.md", "soul.md", "user.md", "feedback/", "projects/", "ideas/"],
    "claude-brain":      ["claude-brain", "search_transcripts", "search_semantic", "get_recent_summaries", "brain mcp"],
    "claude-code":       ["claude code", "claude-code", "skill ", "subagent", "/skill", "settings.json", "hook"],
    "claude-api":        ["anthropic sdk", "anthropic-ai/sdk", "claude api", "prompt cache", "tool use"],

    # Tech stack — keep the ones you use, delete the rest.
    "typescript":        ["typescript", ".tsx", "next.js", "nextjs", "node ", "pnpm"],
    "python":            ["python", "pip ", "venv", "pyproject", ".py "],
    "git-ops":           ["git commit", "git push", "git log", "git pull", "git rebase", "git diff"],

    # Infrastructure
    "containers":        ["docker", "compose.yml", "dockerfile"],
    "cloud":             ["aws", "terraform", "kubernetes", "gcp", "azure", "vercel"],

    # Process
    "feedback-rule":     ["feedback rule", "anti-pattern", "anti pattern", "standing rule", "feedback/"],
    "meta-learning":     ["learn to learn", "meta-learning", "self-noticing", "session-reflect", "capture layer"],
}


# Human-readable category descriptions (for brain_tag_review.py and similar UIs)
TAG_DESCRIPTIONS: dict[str, str] = {
    # EXAMPLE projects — replace these with your own.
    "webapp":            "EXAMPLE project — a web application",
    "research":          "EXAMPLE project — research / notes",
    "content":           "EXAMPLE project — content / writing",
    "harness":           "This harness — memory, persona, standing rules",
    "claude-brain":      "claude-brain transcript persistence layer",
    "claude-code":       "Claude Code harness — skills, hooks, MCP, settings",
    "claude-api":        "Anthropic SDK / Claude API work",
    "typescript":        "TypeScript / Next.js / Node",
    "python":            "Python work",
    "git-ops":           "git operations",
    "containers":        "Docker / containerization",
    "cloud":             "Cloud infrastructure — AWS, Terraform, Kubernetes",
    "feedback-rule":     "Standing behavioral rules captured to memory",
    "meta-learning":     "Self-improvement loop — capture, reflect, codify",
}
