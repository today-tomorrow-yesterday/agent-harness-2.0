"""claude-brain shared library.

Modules:
  paths  — cross-platform CWD encoding + multi-profile JSONL discovery.
           Replaces the per-file `cwd.replace("/", "-")` + hardcoded
           `~/.claude/projects/<encoded>` pattern that was silently broken
           on Windows in upstream.

  vocab  — single source of truth for TAG_KEYWORDS (used by session-end
           hook + import scripts + brain_tag_review) and TAG_DESCRIPTIONS
           (used by review-UI generators). Your vocabulary; replaced
           upstream's memoir/family/health defaults on the fork-in-place
           commit.

Both modules are pure-Python with no extra dependencies. Importable from
hooks/ and scripts/ by inserting the brain root onto sys.path:

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from lib.paths import find_current_jsonl
    from lib.vocab import TAG_KEYWORDS
"""
