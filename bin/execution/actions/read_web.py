"""v1 action: read-only external fetch (action_class 'read_external', blast none).

An HTTP GET against an explicit per-call domain allowlist (default-deny). Optional
auth header resolved INTERNALLY from the keyring (the model never sees the secret).
Transport is injectable for testing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, ClassVar
from urllib.parse import urlparse


class EgressDenied(Exception):
    """The requested host is not on the action's allowlist."""


def _urllib_fetch(url: str, headers: dict, timeout: float) -> tuple[int, str]:
    import urllib.request
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - allowlisted
        raw = r.read()
        return getattr(r, "status", 200), raw.decode("utf-8", "replace")


def _host_allowed(host: str | None, allowlist) -> bool:
    if not host or not allowlist:
        return False
    for a in allowlist:
        a = a.lower().lstrip(".")
        if host == a or host.endswith("." + a):
            return True
    return False


@dataclass
class ReadWeb:
    url: str
    allowlist: tuple[str, ...] = ()        # default-deny: empty => nothing allowed
    headers: dict = field(default_factory=dict)
    timeout: float = 15.0
    max_bytes: int = 200_000
    transport: Callable[[str, dict, float], tuple[int, str]] | None = None

    name: ClassVar[str] = "read_web"
    action_class: ClassVar[str] = "read_external"
    blast_radius: ClassVar[str] = "none"
    self_risk: ClassVar[str] = "LOW"

    def summary(self) -> str:
        return f"GET {self.url}"

    def run(self) -> Any:
        host = (urlparse(self.url).hostname or "").lower()
        if not _host_allowed(host, self.allowlist):
            raise EgressDenied(f"host '{host}' not in allowlist {tuple(self.allowlist)}")
        fetch = self.transport or _urllib_fetch
        status, text = fetch(self.url, dict(self.headers), self.timeout)
        return {"status": status, "url": self.url, "text": text[: self.max_bytes],
                "truncated": len(text) > self.max_bytes}
