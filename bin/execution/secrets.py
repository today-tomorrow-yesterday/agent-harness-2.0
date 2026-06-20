"""Credential chokepoint: the ONLY code allowed to touch a secret.

OS keychain via `keyring` (cryptfile fallback on WSL2/headless), every value wrapped
in SecretStr so it renders '********' anywhere it leaks. The model never receives a
secret as a parameter — a tool calls get() internally and only .get_secret_value()
unwraps at the request boundary. Fetched values auto-register with redaction.
"""
from __future__ import annotations

import os

try:
    import keyring as _keyring
except Exception:  # noqa: BLE001 — keyring optional; module must still import
    _keyring = None

from execution import redaction

_MASK = "********"

# Namespace under which secrets are stored in the OS keychain. Generic, not tied to
# any particular operator or deployment.
_SERVICE_NS = "agent-harness"


class SecretsUnavailable(RuntimeError):
    """keyring is not installed / no usable backend."""


class SecretNotFound(KeyError):
    """No secret stored for (service, account)."""


class SecretStr:
    """A string that refuses to render itself. Only .get_secret_value() unwraps."""

    __slots__ = ("_v",)

    def __init__(self, value: str):
        self._v = value

    def get_secret_value(self) -> str:
        return self._v

    def __repr__(self) -> str:
        return f"SecretStr({_MASK})"

    def __str__(self) -> str:
        return _MASK

    def __format__(self, _spec: str) -> str:
        return _MASK


def _is_headless() -> bool:
    return bool(os.environ.get("WSL_DISTRO_NAME")) or not os.environ.get("DBUS_SESSION_BUS_ADDRESS")


def _backend():
    """Resolve the keyring backend, switching to cryptfile on WSL2/headless Linux."""
    if _keyring is None:
        raise SecretsUnavailable("keyring not installed (pip install keyring keyrings.cryptfile)")
    if os.name == "posix" and _is_headless():
        try:
            from keyrings.cryptfile.cryptfile import CryptFileKeyring  # type: ignore
            kr = CryptFileKeyring()
            return kr
        except Exception:  # noqa: BLE001 — fall back to default backend
            pass
    return _keyring


def _svc(service: str) -> str:
    return f"{_SERVICE_NS}/{service}"


def get(service: str, account: str, *, backend=None) -> SecretStr:
    kr = backend or _backend()
    val = kr.get_password(_svc(service), account)
    if val is None:
        raise SecretNotFound(f"{service}/{account}")
    redaction.register_secret(val)
    return SecretStr(val)


def set_secret(service: str, account: str, value: str, *, backend=None) -> None:
    kr = backend or _backend()
    kr.set_password(_svc(service), account, value)


def delete(service: str, account: str, *, backend=None) -> None:
    kr = backend or _backend()
    kr.delete_password(_svc(service), account)
