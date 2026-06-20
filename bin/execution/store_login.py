"""Double-click-friendly credential storer. Prompts for the service, the account
(an identifier such as an email — not secret) and the password/token (hidden via
getpass), stores it in the OS vault via execution.secrets. No terminal knowledge
required.

  python bin/execution/store_login.py            # interactive prompts
  python bin/execution/store_login.py gmail you@example.com
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import getpass  # noqa: E402

from execution import secrets as s  # noqa: E402

BANNER = "=" * 54


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    print(BANNER)
    print("  Store a login in the OS credential vault")
    print(BANNER)

    service = argv[0] if len(argv) >= 1 else input(
        "\nService name (e.g. gmail, github): ").strip()
    if not service:
        print("No service entered. Nothing stored.")
        return 1

    account = argv[1] if len(argv) >= 2 else input(
        "Account / identifier (e.g. you@example.com): ").strip()
    if not account:
        print("No account entered. Nothing stored.")
        return 1

    print("\nNow the password / token.")
    print("It is HIDDEN as you paste/type — you will see NOTHING. That is correct.")
    pw = getpass.getpass("Password/token (hidden), then press Enter: ")
    if not pw:
        print("No value entered. Nothing stored.")
        return 1

    s.set_secret(service, account, pw)
    print(f"\n[OK] Stored the '{service}' login for {account} in the vault.")
    print("     The value was never shown and is not in any log.")
    print("\nYou can close this window.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
