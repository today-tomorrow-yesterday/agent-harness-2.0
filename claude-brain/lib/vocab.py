"""Tre's tag vocabulary — the canonical TAG_KEYWORDS dict.

Used by `hooks/session-end.py` for live session tagging, and by
`scripts/import_*.py` + `scripts/brain_tag_review.py` for batch/CLI
operations. Single source of truth so the dict can't drift across files.

Original mikeadolan vocabulary (memoir editing, family/health/legal/home
domains) replaced 2026-05-24 when the brain was forked-in-place from
upstream into agent-os.
"""

from __future__ import annotations


TAG_KEYWORDS: dict[str, list[str]] = {
    # Work / consultancy
    "ses":               ["ses", "223-mm", "modular-monolith", "modular template", "modular-template", "sales module", "customer module", "inventory module"],
    "mosaic":            ["mosaic", "mosaic-platform", "mosaic-architecture", "turborepo", "convex", "clerk"],

    # Agent infrastructure
    "agent-os":          ["agent-os", "memory.md", "soul.md", "user.md", "feedback/", "projects/", "ideas/"],
    "claude-brain":      ["claude-brain", "search_transcripts", "search_semantic", "get_recent_summaries", "brain mcp"],
    "claude-code":       ["claude code", "claude-code", "skill ", "subagent", "/skill", "settings.json", "hook"],
    "claude-api":        ["anthropic sdk", "anthropic-ai/sdk", "claude api", "prompt cache", "tool use"],

    # CLONE / Karpathy patterns
    "clone":             ["clone", "expert roster", "experts/", "techniques/", "strategies/", "wiki layer"],
    "karpathy":          ["karpathy", "llm os", "knowledge base"],
    "farmer":            ["farmer", "farmer-youtube", "00_inbox", "ingest.py", "watchlist"],

    # AI video gen
    "cinematic-content": ["cinematic", "scene plate", "character sheet", "seedance", "higgsfield", "banana pro", "soul cinema", "kpop", "k-pop"],
    "ai-video":          ["ai video", "video generation", "yt-dlp", "ffmpeg", "whisper"],

    # Tech stack
    "csharp-dotnet":     ["c#", "csharp", ".net", "dotnet", "ef core", "entity framework"],
    "typescript":        ["typescript", ".tsx", "next.js", "nextjs", "node ", "pnpm"],
    "python":            ["python", "pip ", "venv", "pyproject", ".py "],
    "powershell":        ["powershell", ".ps1", "pwsh", "scheduled task"],
    "git-ops":           ["git commit", "git push", "git log", "git pull", "git rebase", "git diff"],

    # Infrastructure
    "windows":           ["windows", "wsl", "powershell", "scheduled task"],
    "containers":        ["docker", "compose.yml", "dockerfile"],
    "cloud":             ["aws", "terraform", "kubernetes", "gcp", "azure", "vercel"],

    # Process / identity
    "neurodivergence":   ["neurodivergent", "adhd", "dyslexia", "stt", "speech-to-text", "dictation"],
    "feedback-rule":     ["feedback rule", "anti-pattern", "anti pattern", "standing rule", "feedback/"],
    "meta-learning":     ["learn to learn", "meta-learning", "self-noticing", "session-reflect", "capture layer"],

    # Goals / vision
    "ai-influencer":     ["ai influencer", "affiliate marketing", "monetization"],
    "ownership":         ["owned not rented", "owned, not rented", "self-hosted", "vendor lock", "lock-in", "lock in"],
}


# Human-readable category descriptions (for brain_tag_review.py and similar UIs)
TAG_DESCRIPTIONS: dict[str, str] = {
    "agent-os":          "Personal AI OS — memory, persona, standing rules",
    "claude-brain":      "claude-brain transcript persistence layer (forked from mikeadolan)",
    "claude-code":       "Claude Code harness — skills, hooks, MCP, settings",
    "claude-api":        "Anthropic SDK / Claude API work",
    "clone":             "CLONE — Karpathy-style expert knowledge wiki",
    "karpathy":          "Karpathy LLM-OS pattern — knowledge layer, LLM-maintained from raw sources",
    "farmer":            "Source farmers — automated ingestion from YouTube, Slack, etc.",
    "cinematic-content": "AI cinematic image / video work — Seedance, Higgsfield, Banana Pro",
    "ai-video":          "AI video generation tooling — yt-dlp, ffmpeg, Whisper",
    "csharp-dotnet":     "C# / .NET / EF Core",
    "typescript":        "TypeScript / Next.js / Node",
    "python":            "Python work",
    "powershell":        "PowerShell scripting on Windows",
    "git-ops":           "git operations",
    "windows":           "Windows-specific work (WSL, scheduled tasks, PowerShell)",
    "containers":        "Docker / containerization",
    "cloud":             "Cloud infrastructure — AWS, Terraform, Kubernetes",
    "neurodivergence":   "Working with ADHD / dyslexia / STT dictation",
    "feedback-rule":     "Standing behavioral rules captured to memory",
    "meta-learning":     "Self-improvement loop — capture, reflect, codify",
    "ai-influencer":     "AI influencer / affiliate marketing direction",
    "ownership":         "Owned-not-rented infrastructure preferences",
}
