"""CLI for the Execution Layer.

  python -m execution.cli approvals                      # list pending
  python -m execution.cli approve <id> [--by operator]   # approve a parked action
  python -m execution.cli reject  <id> [--by operator]
  python -m execution.cli read <url> --allow host[,host] # smoke-test read_external

Run from bin/ (so `execution` and `runner` resolve as packages).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from execution import approval  # noqa: E402
from execution.actions.read_web import ReadWeb  # noqa: E402
from execution.execute import execute  # noqa: E402


def _cmd_approvals(_args) -> int:
    rows = approval.pending()
    if not rows:
        print("No pending approvals.")
        return 0
    for r in rows:
        print(f"#{r['id']}  [{r['action_class']}/{r['risk_level']}]  {r['summary']}")
    return 0


def _cmd_resolve(args, approved: bool) -> int:
    ok = approval.resolve(args.id, approved, by=args.by)
    verb = "approved" if approved else "rejected"
    print(f"#{args.id} {verb}." if ok else f"#{args.id} not pending (already resolved?).")
    return 0 if ok else 1


def _cmd_read(args) -> int:
    allow = tuple(h.strip() for h in args.allow.split(",") if h.strip())
    res = execute(ReadWeb(url=args.url, allowlist=allow))
    print(f"decision={res['decision']} status={res['status']} risk={res['risk']}")
    if res["result"]:
        print(res["result"]["text"][:500])
    return 0 if res["status"] in ("done", "pending") else 1


def _cmd_secret(args) -> int:
    import getpass
    from execution import secrets as secrets_mod
    print(f"Storing a secret for {args.service}/{args.account}.")
    print("Type/paste the value at the prompt — it is HIDDEN and never shown or logged.")
    val = getpass.getpass("value (hidden): ")
    if not val:
        print("Empty input — nothing stored.")
        return 1
    secrets_mod.set_secret(args.service, args.account, val)
    print(f"Stored {args.service}/{args.account} in the vault. (the value was not displayed)")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="execution.cli")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("approvals").set_defaults(fn=lambda a: _cmd_approvals(a))

    for name, approved in (("approve", True), ("reject", False)):
        sp = sub.add_parser(name)
        sp.add_argument("id", type=int)
        sp.add_argument("--by", default="operator")
        sp.set_defaults(fn=(lambda ap: (lambda a: _cmd_resolve(a, ap)))(approved))

    sp = sub.add_parser("read")
    sp.add_argument("url")
    sp.add_argument("--allow", required=True, help="comma-separated allowlist hosts")
    sp.set_defaults(fn=_cmd_read)

    sp = sub.add_parser("secret")
    sp.add_argument("service")
    sp.add_argument("account")
    sp.set_defaults(fn=_cmd_secret)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
