"""_hook_common.py -- small helpers shared by the hooks in bin/hooks/.

Not a hook itself (the leading underscore keeps it out of the hook catalog and the stdin smoke
test). stdlib only and no I/O at import time: a PreToolUse hook runs on EVERY matching tool call,
so importing this must stay cheap.

Every path is resolved from this file or from the user's home directory. Nothing here knows about
a particular machine, drive or user.
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path

# bin/hooks/_hook_common.py -> bin/hooks -> bin -> repo root
HOOKS_DIR = Path(__file__).resolve().parent
BIN = HOOKS_DIR.parent
ROOT = BIN.parent

_QUOTED = re.compile(r"\"[^\"]*\"|'[^']*'")


def hooks_disabled() -> bool:
    """The repo-wide kill switch, plus the brain's recursion flag.

    HARNESS_HOOKS_DISABLED=1 turns every hook in bin/hooks off. CLAUDE_BRAIN_SKIP_HOOKS=1 is set on
    child `claude -p` processes spawned by the harness itself, so a hook never re-fires inside a
    subprocess another hook started.
    """
    return (os.environ.get("HARNESS_HOOKS_DISABLED") == "1"
            or os.environ.get("CLAUDE_BRAIN_SKIP_HOOKS") == "1")


def unattended() -> bool:
    """True in a headless/scheduled run where no human is present to approve anything.

    Set HARNESS_UNATTENDED=1 in the environment of any unattended `claude -p` run.
    """
    return os.environ.get("HARNESS_UNATTENDED") == "1"


def read_payload() -> dict | None:
    """Parse the hook's stdin. Anything that is not a JSON object -> None (caller allows)."""
    try:
        raw = sys.stdin.read()
    except Exception:
        return None
    if not raw or not raw.strip():
        return None
    try:
        data = json.loads(raw)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def tool_input(data: dict) -> dict:
    ti = data.get("tool_input")
    return ti if isinstance(ti, dict) else {}


def strip_quoted(command: str) -> str:
    """Blank out quoted substrings so data (grep patterns, echo text, commit messages) cannot trip
    command-shaped REGEX patterns.

    Only safe for patterns that never need a quoted ARGUMENT: blanking `rm -rf "/old project"`
    erases the very target a guard must see. Anything that inspects arguments uses
    `segments()` instead, which keeps quoted arguments as real tokens and only treats the FIRST
    word of a command segment as a command -- so a quoted mention inside `echo "..."` or a commit
    message stays an argument of echo/git, never a command of its own."""
    return _QUOTED.sub('""', command)


# ---- shell lexing ---------------------------------------------------------------------------
#
# A deliberately small, shell-neutral lexer (works for bash, sh, zsh, PowerShell and cmd input
# well enough for guardrails). It splits a command line into SEGMENTS at unquoted ; | & and
# newlines, and each segment into tokens with quotes removed. Backslash is literal except before
# a quote inside double quotes, so Windows paths survive intact.

_SEPARATORS = ";|&\n"
_WRAPPERS = {"sudo", "doas", "command", "builtin", "exec", "nohup", "time", "env", "xargs",
             "nice", "ionice", "stdbuf", "timeout"}
_SHELLS_C = {"sh", "bash", "zsh", "dash", "ksh", "fish"}
_PWSH = {"powershell", "powershell.exe", "pwsh", "pwsh.exe"}


def lex(command: str) -> list[list[str]]:
    """[[token, ...], ...] -- one list per command segment, quotes removed.

    Backslash-quote inside double quotes is an escape in bash but a literal backslash in
    PowerShell and cmd ("C:\\" is a drive root there). If reading it as an escape leaves a
    quote unterminated, the command is re-read with backslashes literal -- otherwise
    `Remove-Item -Recurse "C:\\"` would swallow its own closing quote and the rest of the
    line with it."""
    segs, unterminated = _lex(command, escapes=True)
    if unterminated:
        segs, _ = _lex(command, escapes=False)
    return segs


def _lex(command: str, escapes: bool) -> tuple[list[list[str]], bool]:
    segs: list[list[str]] = []
    cur: list[str] = []
    tok: list[str] = []
    in_tok = False
    quote = ""
    i, n = 0, len(command)
    while i < n:
        c = command[i]
        if quote:
            if c == quote:
                quote = ""
            elif escapes and c == "\\" and quote == '"' and i + 1 < n and command[i + 1] in '"\\':
                i += 1
                tok.append(command[i])
            else:
                tok.append(c)
        elif c in ("'", '"'):
            quote, in_tok = c, True
        elif c.isspace() and c != "\n":
            if in_tok:
                cur.append("".join(tok))
                tok, in_tok = [], False
        elif c in _SEPARATORS:
            if in_tok:
                cur.append("".join(tok))
                tok, in_tok = [], False
            if cur:
                segs.append(cur)
                cur = []
        elif c in "()" and not in_tok:
            pass                                    # subshell / grouping parens
        else:
            tok.append(c)
            in_tok = True
        i += 1
    if in_tok:
        cur.append("".join(tok))
    if cur:
        segs.append(cur)
    return segs, bool(quote)


def _strip_head(seg: list[str]) -> list[str]:
    """Drop leading VAR=value assignments and wrapper commands (sudo, env, xargs, ...) together
    with their option flags, so the real command is first."""
    i = 0
    while i < len(seg):
        t = seg[i]
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", t):
            i += 1
            continue
        w = verb([t])
        if w not in _WRAPPERS:
            break
        i += 1
        while i < len(seg) and seg[i].startswith("-"):
            takes_value = seg[i] in ("-u", "-g", "-s", "-k", "-n", "-I", "-L", "-P")
            i += 2 if takes_value else 1           # sudo -u USER, xargs -I {}, timeout -s SIG
        if w == "timeout" and i < len(seg) and re.fullmatch(r"[\d.]+[smhd]?", seg[i]):
            i += 1                                 # timeout 30 cmd
    return seg[i:]


def segments(command: str, _depth: int = 0) -> list[list[str]]:
    """Command segments with the real command first, INCLUDING commands nested as a string in
    `bash -c "..."`, `pwsh -Command "..."`, `cmd /c "..."` and `eval "..."` (which ARE commands,
    unlike a quoted mention in echo)."""
    out: list[list[str]] = []
    for seg in lex(command or ""):
        seg = _strip_head(seg)
        if not seg:
            continue
        out.append(seg)
        if _depth >= 3:
            continue
        head = verb(seg)
        nested: list[str] = []
        if head in _SHELLS_C or head in _PWSH or head in ("cmd", "cmd.exe"):
            for j, t in enumerate(seg[1:], start=1):
                tl = t.lower()
                if tl in ("-c", "-command", "/c", "/k") or (head in _SHELLS_C and
                                                             re.fullmatch(r"-[a-z]*c", tl)):
                    nested.append(" ".join(seg[j + 1:]) if head in ("cmd", "cmd.exe")
                                  else (seg[j + 1] if j + 1 < len(seg) else ""))
                    break
        elif head == "eval":
            nested.append(" ".join(seg[1:]))
        for inner in nested:
            out.extend(segments(inner, _depth + 1))
    return out


def verb(seg: list[str]) -> str:
    """The command word of a segment, lower-cased, without directory."""
    if not seg:
        return ""
    return re.split(r"[\\/]", seg[0])[-1].lower()


def nested_texts(command: str) -> list[str]:
    """The command plus every nested command string, for regex checks that use strip_quoted()."""
    texts = [command or ""]
    for seg in segments(command):
        texts.append(" ".join(_requote(t) for t in seg))
    return texts


def _requote(t: str) -> str:
    """A token that was a single word stays visible to regex checks (`rm -rf "/"` must still read
    as a root delete); a multi-word or quote-bearing token is data and is blanked, exactly as
    strip_quoted() would blank it."""
    return '""' if (not t or any(ch.isspace() or ch in "\"'" for ch in t)) else t


# ---- inter-process lock ---------------------------------------------------------------------

class FileLock:
    """Exclusive inter-process lock on `<path>`, stdlib only, Windows + POSIX.

    POSIX uses fcntl.flock, Windows msvcrt.locking on byte 0 of the lock file. Both locks are
    released by the OS if the holder dies, so a crashed hook can never wedge the queue.
    Raises TimeoutError if the lock cannot be taken within `timeout` seconds.
    """

    def __init__(self, path: str | Path, timeout: float = 15.0):
        self.path = Path(path)
        self.timeout = timeout
        self._fh = None

    def __enter__(self):
        import time
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.path, "a+b")
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                if os.name == "nt":
                    import msvcrt
                    self._fh.seek(0)
                    msvcrt.locking(self._fh.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except OSError:
                if time.monotonic() >= deadline:
                    self._fh.close()
                    self._fh = None
                    raise TimeoutError(f"could not lock {self.path}")
                time.sleep(0.02)

    def __exit__(self, *exc):
        try:
            if os.name == "nt":
                import msvcrt
                self._fh.seek(0)
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
        finally:
            self._fh.close()
            self._fh = None
        return False


def state_dir(name: str) -> Path:
    """Per-hook runtime state directory.

    Default: <repo>/logs/hook-state/<name>/ (logs/ is gitignored). HARNESS_HOOK_STATE_DIR overrides
    the parent, which is how the tests isolate themselves. Falls back to the system temp dir if the
    repo location is not writable.
    """
    base = os.environ.get("HARNESS_HOOK_STATE_DIR")
    parent = Path(base).expanduser() if base else ROOT / "logs" / "hook-state"
    d = parent / name
    try:
        d.mkdir(parents=True, exist_ok=True)
        return d
    except OSError:
        d = Path(tempfile.gettempdir()) / "harness-hook-state" / name
        d.mkdir(parents=True, exist_ok=True)
        return d


def safe_name(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", s or "no-session")[:120]


def settings_path() -> Path:
    """The Claude Code settings.json, resolved the same way bin/register_hook.py resolves it."""
    override = os.environ.get("CLAUDE_SETTINGS_PATH")
    if override:
        return Path(override).expanduser()
    cfg_dir = os.environ.get("CLAUDE_CONFIG_DIR")
    base = Path(cfg_dir).expanduser() if cfg_dir else Path.home() / ".claude"
    return base / "settings.json"


def same_or_under(path: str | Path, root: str | Path) -> bool:
    """Is `path` equal to or inside `root`? Case-insensitive only where the OS is (Windows)."""
    try:
        p = os.path.normcase(os.path.abspath(str(path)))
        r = os.path.normcase(os.path.abspath(str(root)))
        return os.path.commonpath([p, r]) == r
    except ValueError:            # different drives on Windows
        return False


def emit_context(event: str, text: str) -> None:
    """Advisory output: inject `text` into the model's context without blocking anything."""
    print(json.dumps({
        "hookSpecificOutput": {"hookEventName": event, "additionalContext": text},
        "suppressOutput": True,
    }))


def deny(msg: str) -> int:
    """Deny = exit 2 with the reason on stderr (Claude Code hands it to the model)."""
    try:
        sys.stderr.write(msg.rstrip() + "\n")
    except Exception:
        pass
    return 2
