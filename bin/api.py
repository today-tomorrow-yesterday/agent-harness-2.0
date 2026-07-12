#!/usr/bin/env python3
"""api.py — the agent keyring: call your paid/keyed APIs WITHOUT the key ever
touching the transcript.

THE PROBLEM: keys end up scattered across projects (Gemini, YouTube Data v3,
Google Cloud, Resend, Sketchfab, Supabase, ...) and mid-chat research can't hit
those APIs without someone pasting a credential into context.

THE DESIGN: one gitignored keyring file (bin/secrets/keyring.env) + this wrapper.
Agents compose requests by SERVICE NAME; the key is injected here at request
time and every loaded secret value is scrubbed from anything this tool prints.
Agents may RUN this tool freely but must NEVER read keyring.env directly.

Usage (any Claude session, via the shell):
  python bin/api.py list                      # which services are configured (names only)
  python bin/api.py yt-search "some query" --max 10
  python bin/api.py yt-videos ID1,ID2         # stats/snippet for video ids
  python bin/api.py yt-channel @SomeHandle    # channel lookup
  python bin/api.py get youtube search --param q=canning --param part=snippet
  python bin/api.py post gemini "models/gemini-2.5-flash:generateContent" --json '{"contents":[...]}'
  python bin/api.py get sketchfab "v3/models/<uid>/download"
  python bin/api.py get supabase:PROJ "rest/v1/table_name?select=*&limit=5"

Safety properties:
- Requests go ONLY to the configured service base URLs (no arbitrary-URL fetch).
- GET + POST only; POST body must be JSON; no other methods.
- Output is redacted: any loaded secret value is replaced with ***KEY*** before print.
- File-based, not env-based: works in clean-environment headless runs.
- Never prints or logs the keyring contents; `list` shows names + a config bit only.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
KEYRING = ROOT / "bin" / "secrets" / "keyring.env"
TIMEOUT = 60
UA = "agent-harness-api/1.0 (personal research tooling)"

# Service registry: how each service authenticates. Key names refer to keyring.env.
# auth styles: "query"  -> ?<param>=<key>
#              "header" -> <header>: <prefix><key>
SERVICES = {
    "youtube":  {"base": "https://www.googleapis.com/youtube/v3/",
                 "key": "YOUTUBE_API_KEY", "auth": ("query", "key")},
    "gemini":   {"base": "https://generativelanguage.googleapis.com/v1beta/",
                 "key": "GEMINI_API_KEY", "auth": ("header", "x-goog-api-key", "")},
    "gcp":      {"base": "https://www.googleapis.com/",
                 "key": "GOOGLE_CLOUD_API_KEY", "auth": ("query", "key")},
    "resend":   {"base": "https://api.resend.com/",
                 "key": "RESEND_API_KEY", "auth": ("header", "Authorization", "Bearer ")},
    "sketchfab": {"base": "https://api.sketchfab.com/",
                  "key": "SKETCHFAB_API_TOKEN", "auth": ("header", "Authorization", "Token ")},
    # supabase is multi-project: use service name "supabase:<NAME>" with keyring pairs
    # SUPABASE_<NAME>_URL and SUPABASE_<NAME>_KEY (anon or service role — your choice).
}


def load_keyring() -> dict[str, str]:
    if not KEYRING.exists():
        return {}
    vals = {}
    for line in KEYRING.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\s*([A-Za-z0-9_]+)\s*=\s*(.+?)\s*$", line)
        if m and not m.group(1).startswith("#") and m.group(2) and "PASTE" not in m.group(2):
            vals[m.group(1)] = m.group(2)
    return vals


def redact(text: str, ring: dict[str, str]) -> str:
    for v in ring.values():
        if len(v) >= 8:                      # don't redact trivial strings
            text = text.replace(v, "***KEY***")
            text = text.replace(urllib.parse.quote(v, safe=""), "***KEY***")
    return text


def resolve_service(name: str, ring: dict) -> tuple[str, str, tuple]:
    """-> (base_url, key_value, auth_spec). Exits with a helpful message if unset."""
    if name.startswith("supabase:"):
        proj = name.split(":", 1)[1].upper()
        url, key = ring.get(f"SUPABASE_{proj}_URL"), ring.get(f"SUPABASE_{proj}_KEY")
        if not url or not key:
            sys.exit(f"supabase project '{proj}' not in keyring (needs SUPABASE_{proj}_URL + SUPABASE_{proj}_KEY). Run `api.py list`.")
        return url.rstrip("/") + "/", key, ("supabase",)
    svc = SERVICES.get(name)
    if not svc:
        sys.exit(f"unknown service '{name}'. Known: {', '.join(SERVICES)} + supabase:<NAME>. Run `api.py list`.")
    key = ring.get(svc["key"])
    if not key:
        sys.exit(f"service '{name}' has no key configured ({svc['key']} missing in keyring). Run `api.py list`.")
    return svc["base"], key, svc["auth"]


def call(service: str, path: str, params: dict, body: dict | None, ring: dict) -> str:
    base, key, auth = resolve_service(service, ring)
    if path.startswith(("http://", "https://")):
        sys.exit("pass a PATH relative to the service base, not a full URL (allowlist by construction).")
    url = base + path.lstrip("/")
    headers = {"User-Agent": UA, "Accept": "application/json"}
    if auth[0] == "query":
        params = dict(params); params[auth[1]] = key
    elif auth[0] == "header":
        headers[auth[1]] = auth[2] + key
    elif auth[0] == "supabase":
        headers["apikey"] = key
        headers["Authorization"] = "Bearer " + key
    if params:
        sep = "&" if "?" in url else "?"
        url = url + sep + urllib.parse.urlencode(params)
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers,
                                 method="POST" if body is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return json.dumps({"http_error": e.code,
                           "body": e.read().decode("utf-8", errors="replace")[:4000]})
    except Exception as e:
        return json.dumps({"error": str(e)})


def parse_params(pairs: list[str]) -> dict:
    out = {}
    for p in pairs or []:
        if "=" not in p:
            sys.exit(f"--param must be k=v (got: {p})")
        k, v = p.split("=", 1)
        out[k] = v
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Keyring-backed API caller (keys never printed).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="show configured vs missing services (names only, never values)")
    g = sub.add_parser("get");  g.add_argument("service"); g.add_argument("path"); g.add_argument("--param", action="append")
    p = sub.add_parser("post"); p.add_argument("service"); p.add_argument("path"); p.add_argument("--param", action="append"); p.add_argument("--json", required=True)
    ys = sub.add_parser("yt-search");  ys.add_argument("query"); ys.add_argument("--max", type=int, default=10); ys.add_argument("--type", default="video"); ys.add_argument("--order", default="relevance")
    yv = sub.add_parser("yt-videos");  yv.add_argument("ids", help="comma-separated video ids")
    yc = sub.add_parser("yt-channel"); yc.add_argument("handle", help="@handle or channel id")
    args = ap.parse_args(argv)

    ring = load_keyring()

    if args.cmd == "list":
        rows = []
        for name, svc in SERVICES.items():
            rows.append(f"  {'[x]' if ring.get(svc['key']) else '[ ]'} {name:<10} ({svc['key']})")
        projs = sorted({m.group(1) for k in ring
                        if (m := re.match(r"SUPABASE_([A-Z0-9_]+)_URL$", k))})
        for pr in projs:
            ok = f"SUPABASE_{pr}_KEY" in ring
            rows.append(f"  {'[x]' if ok else '[ ]'} supabase:{pr.lower()}")
        print("Configured services ([x] = key present; values are never shown):")
        print("\n".join(rows) if rows else "  (keyring empty or missing)")
        if not KEYRING.exists():
            print(f"\nKeyring not found. Copy keyring.env.template -> {KEYRING.name} in bin/secrets/ and fill it.")
        return 0

    if args.cmd == "get":
        out = call(args.service, args.path, parse_params(args.param), None, ring)
    elif args.cmd == "post":
        try:
            body = json.loads(args.json)
        except ValueError as e:
            sys.exit(f"--json is not valid JSON: {e}")
        out = call(args.service, args.path, parse_params(args.param), body, ring)
    elif args.cmd == "yt-search":
        out = call("youtube", "search", {"part": "snippet", "q": args.query, "type": args.type,
                                         "maxResults": str(args.max), "order": args.order}, None, ring)
    elif args.cmd == "yt-videos":
        out = call("youtube", "videos", {"part": "snippet,statistics,contentDetails",
                                         "id": args.ids}, None, ring)
    elif args.cmd == "yt-channel":
        params = {"part": "snippet,statistics"}
        if args.handle.startswith("@"):
            params["forHandle"] = args.handle
        else:
            params["id"] = args.handle
        out = call("youtube", "channels", params, None, ring)
    else:                                    # unreachable; argparse enforces
        return 1

    print(redact(out, ring))
    return 0


if __name__ == "__main__":
    sys.exit(main())
