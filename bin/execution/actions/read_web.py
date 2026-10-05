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


def _urllib_fetch(url: str, headers: dict, timeout: float,
                  max_bytes: int = 200_000) -> tuple[int, str, str]:
    """GET `url` WITHOUT following redirects, returning (status, text, final_url).

    The default opener installs HTTPRedirectHandler, which silently follows 30x. The
    allowlist is checked once, against the URL the caller supplied — so an allowlisted
    host answering `302 Location: https://elsewhere.example/` would hand the fetch to
    an unlisted host while the audit log still named the allowlisted one. Default-deny
    means the host that actually serves the bytes is the one that must be on the
    list, so the redirect is refused outright and run() re-checks the final host.

    `max_bytes` is applied AT THE READ, not to the returned string: an earlier version
    materialised a huge body in full before truncating it.
    """
    import urllib.request

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None   # -> urllib raises HTTPError instead of following

    opener = urllib.request.build_opener(_NoRedirect)
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    with opener.open(req, timeout=timeout) as r:  # noqa: S310 - allowlisted + no-redirect
        raw = r.read(max_bytes + 1)
        return (getattr(r, "status", 200), raw.decode("utf-8", "replace"),
                getattr(r, "url", url) or url)


def _host_allowed(host: str | None, allowlist) -> bool:
    if not host or not allowlist:
        return False
    for a in allowlist:
        a = a.lower().strip()
        a = a[1:] if a.startswith(".") else a   # strip ONE leading dot, not all
        if "." not in a:
            continue   # reject single-label entries (e.g. "com") — they match every host
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
    # A transport returns (status, text) or (status, text, final_url).
    transport: Callable[[str, dict, float], tuple] | None = None

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
        if self.transport is not None:
            res = self.transport(self.url, dict(self.headers), self.timeout)
        else:
            res = _urllib_fetch(self.url, dict(self.headers), self.timeout, self.max_bytes)
        if len(res) == 3:
            status, text, final_url = res
        else:
            status, text = res
            final_url = self.url

        # Re-check the host that ACTUALLY served the bytes. _urllib_fetch refuses
        # redirects, but an injected transport may follow them; the allowlist is only
        # default-deny if the final host is on it, and the audit trail must name it.
        final_host = (urlparse(final_url).hostname or "").lower()
        if final_host != host and not _host_allowed(final_host, self.allowlist):
            raise EgressDenied(
                f"redirected to host '{final_host}' not in allowlist {tuple(self.allowlist)}")

        return {"status": status, "url": final_url, "text": text[: self.max_bytes],
                "truncated": len(text) > self.max_bytes}
