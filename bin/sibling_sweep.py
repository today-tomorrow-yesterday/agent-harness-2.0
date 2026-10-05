#!/usr/bin/env python3
"""sibling_sweep.py — find the copies of a bug that the original fix never reached.

THE PATTERN THIS EXISTS FOR. The same shape turns up again and again:

    a defect is discovered in one file
    it is fixed in that file
    a comment is written explaining the incident
    the identical defect stays untouched in three sibling files

None of these is subtle. Each stays invisible because nobody asks the second question —
not "is this file fixed?" but "which other files have this?". A code review answers the
first; only a sweep answers the second. So: A FIX IS NOT DONE UNTIL ITS SIBLINGS ARE
CHECKED, and this module is how a machine checks it every day.

Rules (each is a defect that has actually shipped, more than once, in programs like these):
  dry-run-writes-health           a --dry-run/--print mode that still writes the outcome
                                  sidecar or pages, without calling set_dry_run()
  claude-p-without-clean-env      spawns `claude -p` without harness_common.clean_env, so a
                                  metered API key in the environment moves the job onto paid
                                  per-token billing
  prefix-check-called-an-allowlist  a start-anchored regex used as an allowlist — everything
                                  after a valid prefix is unchecked
  mtime-as-content-age            an AGE derived from mtime (a clone, a move or a checkout
                                  rewrites mtime)
  shell-grant-without-untrusted-rule  a Bash tool grant with no untrusted-input rule stated

Suppress a deliberate use with a pragma ON or just above the line that NAMES the rule:
    # sibling-sweep: ok <rule-name> — <reason>
A pragma that does not name the rule does not suppress it (and is itself reported).

Read-only. `--strict` exits 1 when anything is found, so a scheduled job can gate on it.

    python bin/sibling_sweep.py
    python bin/sibling_sweep.py --root path/to/dir --strict
"""
from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

BIN = Path(__file__).resolve().parent
DEFAULT_ROOTS = (BIN,)
SKIP_DIRS = {"tests", "__pycache__"}


@dataclass
class Finding:
    rule: str
    file: str
    line: int
    detail: str
    why: str


@dataclass
class Rule:
    name: str
    why: str
    check: object
    findings: list[Finding] = field(default_factory=list)


def _ln(text: str, idx: int) -> int:
    return text[:max(idx, 0)].count("\n") + 1


# ── a non-mutating mode that still writes the health record ───────────────────────────
_DRYISH = re.compile(r"""add_argument\(\s*["'](--dry-run|--print|--manifest-only)["']""")


def rule_dry_run(path: Path, text: str) -> list[tuple[int, str]]:
    if "set_dry_run(" in text:
        return []
    flags = [(_ln(text, m.start()), m.group(1)) for m in _DRYISH.finditer(text)]
    if not flags:
        return []
    if not any(k in text for k in ("record_outcome(", "alert(")):
        return []
    ln, flag = flags[0]
    return [(ln, f"declares {flag} and writes an outcome/alert, but never calls set_dry_run()")]


# ── a headless claude spawn that can inherit a metered key ────────────────────────────
_CLAUDE_SPAWN = re.compile(r"""["']-p["']""")


def rule_claude_without_clean_env(path: Path, text: str) -> list[tuple[int, str]]:
    if "claude" not in text.lower() or not _CLAUDE_SPAWN.search(text):
        return []
    if "subprocess" not in text and "Popen" not in text:
        return []
    if "clean_env(" in text:
        return []
    m = _CLAUDE_SPAWN.search(text)
    return [(_ln(text, m.start()), "spawns `claude -p` without clean_env() — a metered API key "
                                   "in the environment would silently override the "
                                   "subscription login")]


# ── a prefix check presented as an allowlist ──────────────────────────────────────────
_ALLOWLIST = re.compile(r"re\.compile\(\s*r?[\"'](\^[^\"']*)[\"']")


def rule_unanchored_allowlist(path: Path, text: str) -> list[tuple[int, str]]:
    out = []
    for m in _ALLOWLIST.finditer(text):
        pat = m.group(1)
        if "$" in pat[-3:] or pat.endswith(r"\Z"):
            continue
        ctx = text[max(0, m.start() - 400):m.start()].lower()
        if not any(w in ctx for w in ("allow", "valid", "refuse", "reject", "safe", "permit")):
            continue
        out.append((_ln(text, m.start()),
                    f"`{pat}` is anchored at the start only — everything after a valid prefix "
                    f"is unchecked, so this is a prefix test, not an allowlist"))
    return out


# ── mtime used as a content clock ─────────────────────────────────────────────────────
_MTIME = re.compile(r"st_mtime|getmtime")


def rule_mtime_as_age(path: Path, text: str) -> list[tuple[int, str]]:
    out = []
    for m in _MTIME.finditer(text):
        window = text[max(0, m.start() - 300):m.start() + 300]
        if "86400" not in window and "/ 3600" not in window and "3600" not in window:
            continue
        out.append((_ln(text, m.start()),
                    "derives an AGE from mtime. After a clone, move or checkout mtime is the "
                    "touch date, not the content date — use git dates, or a timestamp the "
                    "program itself recorded"))
    return out


# ── a shell grant with no untrusted-input rule ────────────────────────────────────────
_GRANT = re.compile(r"""(?<!dis)(?:--allowed-tools|allowedTools)["']?\s*[,=:]?\s*["']([^"'\n]*)""")


def rule_shell_without_fence(path: Path, text: str) -> list[tuple[int, str]]:
    if "UNTRUSTED" in text.upper():
        return []
    # Only an actual GRANT counts: `--disallowed-tools "... Bash ..."` is the opposite.
    for m in _GRANT.finditer(text):
        if re.search(r"\bBash\b", m.group(1)):
            return [(_ln(text, m.start()),
                     "grants Bash to a model with no untrusted-input rule in the prompt — if it "
                     "ever reads fetched or user-supplied content, that content can steer a "
                     "shell")]
    return []


RULES = [
    Rule("dry-run-writes-health", "A diagnostic run must not destroy the health record of the "
         "last real one, or page anyone.", rule_dry_run),
    Rule("claude-p-without-clean-env", "A headless spawn that inherits a metered key bills "
         "per token instead of using the subscription.", rule_claude_without_clean_env),
    Rule("prefix-check-called-an-allowlist", "`re.match` anchors the start only.",
         rule_unanchored_allowlist),
    Rule("mtime-as-content-age", "mtime answers 'when was this touched', never 'how old is "
         "this'.", rule_mtime_as_age),
    Rule("shell-grant-without-untrusted-rule", "A shell grant needs the untrusted-input "
         "constraint stated, not implied.", rule_shell_without_fence),
]


def sweep(root: Path = BIN) -> list[Rule]:
    rules = [Rule(r.name, r.why, r.check) for r in RULES]
    for p in sorted(Path(root).rglob("*.py")):
        if any(part in SKIP_DIRS for part in p.relative_to(root).parts):
            continue
        if p.resolve() == Path(__file__).resolve():
            continue
        try:
            text = p.read_text(encoding="utf-8-sig", errors="replace")
            ast.parse(text)
        except (OSError, SyntaxError, ValueError):
            continue
        rel = p.relative_to(root).as_posix()
        lines = text.splitlines()
        for r in rules:
            for ln, detail in r.check(p, text):
                ctx = "\n".join(lines[max(0, ln - 3):ln + 1])
                if re.search(rf"sibling-sweep:\s*ok\b[^\n]*{re.escape(r.name)}", ctx):
                    continue
                if re.search(r"sibling-sweep:\s*ok\b", ctx):
                    detail += ("  (a nearby `sibling-sweep: ok` pragma does not name this "
                               "rule, so it does not suppress it)")
                r.findings.append(Finding(r.name, rel, ln, detail, r.why))
    return rules


def sweep_roots(roots) -> tuple[list[Rule], list[Path]]:
    merged = {r.name: Rule(r.name, r.why, r.check) for r in RULES}
    checked = []
    for root in roots:
        root = Path(root)
        if not root.is_dir():
            continue
        checked.append(root)
        for r in sweep(root):
            for f in r.findings:
                merged[r.name].findings.append(
                    Finding(f.rule, f"{root.name}/{f.file}", f.line, f.detail, f.why))
    return list(merged.values()), checked


def render(rules: list[Rule], roots: list[Path] | None = None) -> list[str]:
    total = sum(len(r.findings) for r in rules)
    L = ["## Sibling sweep — the same bug, in the files the fix never reached", ""]
    if roots:
        L += [f"- checked: {', '.join(r.name + '/' for r in roots)}", ""]
    if not total:
        return L + ["- No known defect pattern has an unfixed sibling.", ""]
    L += [f"- **{total} finding(s)** across {sum(1 for r in rules if r.findings)} pattern(s).", ""]
    for r in rules:
        if r.findings:
            L.append(f"- **{r.name}** — {r.why}")
            L += [f"    - `{f.file}:{f.line}` — {f.detail}" for f in r.findings]
            L.append("")
    return L


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Find unfixed copies of already-fixed bugs.")
    ap.add_argument("--root", default=None, help="sweep only this directory (default: bin/)")
    ap.add_argument("--strict", action="store_true", help="exit 1 if anything is found")
    args = ap.parse_args(argv)
    rules, roots = sweep_roots([Path(args.root)] if args.root else DEFAULT_ROOTS)
    if not roots:
        print(f"nothing to sweep: {args.root} is not a directory")
        return 2
    print("\n".join(render(rules, roots)))
    total = sum(len(r.findings) for r in rules)
    return 1 if (args.strict and total) else 0


if __name__ == "__main__":
    sys.exit(main())
