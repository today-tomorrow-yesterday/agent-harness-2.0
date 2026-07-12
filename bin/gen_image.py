#!/usr/bin/env python3
"""gen_image.py — generate an image via Gemini image models using the api.py keyring.

Saves the PNG to disk and prints ONLY the file path + usage metadata (never the
base64, never a key). Reuses api.py's loader/caller so all keyring safety
properties hold.

Usage:
  python bin/gen_image.py "prompt text" --out out.png [--model gemini-2.5-flash-image]
  python bin/gen_image.py "same character, back view" --ref front.png --out back.png

--ref (repeatable) sends reference image(s) as inline parts — the model
conditions on them, which is the character-consistency / multi-view trick:
generate one canonical view, then request other angles "of this exact subject".
"""
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from api import call, load_keyring, redact  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("prompt")
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="gemini-2.5-flash-image")
    ap.add_argument("--ref", action="append", default=[],
                    help="reference image path (repeatable) — conditions generation on it")
    args = ap.parse_args()

    ring = load_keyring()
    parts: list[dict] = []
    for ref in args.ref:
        rp = Path(ref)
        if not rp.exists():
            print(f"ref not found: {ref}")
            return 1
        mime = mimetypes.guess_type(rp.name)[0] or "image/png"
        parts.append({"inline_data": {"mime_type": mime,
                                      "data": base64.b64encode(rp.read_bytes()).decode()}})
    parts.append({"text": args.prompt})
    body = {"contents": [{"parts": parts}]}
    raw = call("gemini", f"models/{args.model}:generateContent", {}, body, ring)
    try:
        resp = json.loads(raw)
    except ValueError:
        print(redact(raw[:2000], ring))
        return 1
    if "error" in resp or "http_error" in resp:
        print(redact(json.dumps(resp)[:2000], ring))
        return 1

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    saved = False
    for part in resp.get("candidates", [{}])[0].get("content", {}).get("parts", []):
        blob = part.get("inlineData") or part.get("inline_data")
        if blob and blob.get("data"):
            out.write_bytes(base64.b64decode(blob["data"]))
            saved = True
            break
    if not saved:
        print("no image in response; text parts follow:")
        for part in resp.get("candidates", [{}])[0].get("content", {}).get("parts", []):
            if part.get("text"):
                print(redact(part["text"][:1500], ring))
        return 1

    usage = resp.get("usageMetadata", {})
    print(json.dumps({"saved": str(out), "bytes": out.stat().st_size,
                      "usage": {k: usage.get(k) for k in
                                ("promptTokenCount", "candidatesTokenCount", "totalTokenCount")}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
