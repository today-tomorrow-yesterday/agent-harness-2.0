"""notify_slack: markdown conversion, the egress secret scrub, two-route delivery and
dry-run. No test touches the network: every send path is either dry-run or has
urlopen replaced by a function that fails the test if reached."""
import sys
from pathlib import Path

import pytest

BIN = Path(__file__).resolve().parents[1]
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

import notify_slack as ns  # noqa: E402
from notify_slack import to_slack_mrkdwn  # noqa: E402

FAKE_HOOK = "https://hooks.slack.com/services/T000/B000/FAKEMAIN"
FAKE_DIGEST = "https://hooks.slack.com/services/T000/B000/FAKEDIGEST"


# --------------------------------------------------------------- markdown -> mrkdwn
def test_headers_become_bold_lines():
    assert to_slack_mrkdwn("# Title") == "*Title*"
    assert to_slack_mrkdwn("### Sub") == "*Sub*"


def test_double_asterisk_bold_becomes_single():
    assert to_slack_mrkdwn("**runs** today") == "*runs* today"


def test_dash_bullets_become_dots():
    assert to_slack_mrkdwn("- item") == "• item"
    assert to_slack_mrkdwn("  - nested") == "  • nested"


def test_code_and_emoji_pass_through():
    assert to_slack_mrkdwn("`python x.py` 🟢 ✅") == "`python x.py` 🟢 ✅"


# --------------------------------------------------------------- egress secret scrub
SECRETS = {
    "aws_access_key": "AKIAIOSFODNN7EXAMPLE",
    "github_pat": "ghp_16CharsAtLeastxxxxxxxxxxxxxxxxxxxxxx",
    "pem_header": "-----BEGIN RSA PRIVATE KEY-----",
    "google_api_key": "AIzaSyD-1234567890abcdefghijklmnopqrstu",
    "assignment_token": "SOME_API_TOKEN=abcdef0123456789ABCDEFghijklmnop012345",
    "bearer": "Bearer abc.def-123",
    "sk_key": "sk-ABCDEFGH12345678ABCD",
    "slack_token": "xoxb-123456789012-abcdefghijkl",
    "jwt": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
    "long_hex": "deadbeefdeadbeefdeadbeefdeadbeef",
}


def _scrubbers():
    from execution.redaction import scrub
    from execution.secret_patterns import scrub_shapes
    return {"execution.redaction.scrub": scrub,
            "secret_patterns.scrub_shapes": scrub_shapes,
            "notify_slack._egress_scrub": ns._egress_scrub}


@pytest.mark.parametrize("label,value", sorted(SECRETS.items()))
@pytest.mark.parametrize("sname", sorted(_scrubbers()))
def test_every_scrubber_masks_every_secret_shape(sname, label, value):
    """The failure this guards was DIVERGENCE between scrubbers, so the assertion is
    the full cross-product: every scrubber masks every shape."""
    out = _scrubbers()[sname](f"prefix {value} suffix")
    assert value not in out, f"{sname} leaked {label}: {out!r}"
    assert "[REDACTED]" in out


@pytest.mark.parametrize("benign", [
    "job weekly-planner produced 12 items in 4.2s",
    "37 of 37 tasks still interactive",
    "re-ran the digest (failed 0x1, attempt 1/2 in 24h)",
    "Tasks audited: 37/37",
])
def test_scrubbing_does_not_mangle_ordinary_text(benign):
    """A scrubber that redacts normal log lines gets switched off."""
    assert ns._egress_scrub(benign) == benign


def test_fallback_scrub_uses_the_canonical_list(monkeypatch):
    """If execution.redaction cannot be imported, the fallback must still be the full
    canonical list — not a weaker hand-copied subset."""
    monkeypatch.setitem(sys.modules, "execution.redaction", None)   # import -> ImportError
    for value in SECRETS.values():
        assert value not in ns._egress_scrub(f"x {value} y")


def test_scrub_fails_closed_when_no_scrubber_loads(monkeypatch):
    import importlib.util
    monkeypatch.setitem(sys.modules, "execution.redaction", None)

    def broken(*_a, **_k):
        raise ImportError("simulated")
    monkeypatch.setattr(importlib.util, "spec_from_file_location", broken)
    out = ns._egress_scrub("token sk-ABCDEFGH12345678ABCD")
    assert "sk-ABCDEFGH" not in out and "withheld" in out


# --------------------------------------------------------------- routing + dry-run
@pytest.fixture
def hooks(tmp_path, monkeypatch):
    """Point both webhook files at tmp paths and clear the env overrides."""
    main = tmp_path / "hook.txt"
    digest = tmp_path / "hook-digest.txt"
    monkeypatch.setattr(ns, "WEBHOOK_FILE", main)
    monkeypatch.setattr(ns, "DIGEST_WEBHOOK_FILE", digest)
    for var in ("SLACK_WEBHOOK_URL", "SLACK_WEBHOOK_DIGEST_URL", ns.DRY_RUN_ENV):
        monkeypatch.delenv(var, raising=False)

    def no_network(*_a, **_k):
        raise AssertionError("network reached")
    monkeypatch.setattr(ns.urllib.request, "urlopen", no_network)

    def wire(main_hook=True, digest_hook=False):
        if main_hook:
            main.write_text(FAKE_HOOK, encoding="utf-8")
        if digest_hook:
            digest.write_text(FAKE_DIGEST, encoding="utf-8")
    return wire


def test_nothing_configured_is_a_noop(hooks):
    hooks(main_hook=False)
    assert ns.post_slack("hi") is None
    assert ns.post_slack("hi", route="digest") is None


def test_digest_falls_back_to_the_main_webhook_until_its_own_exists(hooks):
    hooks(digest_hook=False)
    assert ns._resolve_webhook("digest") == (FAKE_HOOK, "alerts")


def test_digest_webhook_is_picked_up_when_configured(hooks):
    hooks(digest_hook=True)
    assert ns._resolve_webhook("digest") == (FAKE_DIGEST, "digest")


def test_digest_only_configuration_still_routes_digest(hooks):
    hooks(main_hook=False, digest_hook=True)
    assert ns._resolve_webhook("digest") == (FAKE_DIGEST, "digest")
    assert ns._resolve_webhook("alerts") == (None, "alerts")   # alerts never use digest


def test_alerts_route_never_uses_the_digest_webhook(hooks):
    hooks(digest_hook=True)
    assert ns._resolve_webhook("alerts") == (FAKE_HOOK, "alerts")


def test_env_var_overrides_win(hooks, monkeypatch):
    hooks(digest_hook=True)
    other = "https://hooks.slack.com/services/T000/B000/FROMENV"
    monkeypatch.setenv("SLACK_WEBHOOK_DIGEST_URL", other)
    assert ns._resolve_webhook("digest") == (other, "digest")


def test_invalid_webhook_values_are_ignored(hooks, monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "http://example.com/not-slack")
    hooks(main_hook=False)
    assert ns._resolve_webhook("alerts") == (None, "alerts")


def test_dry_run_posts_nothing(hooks, monkeypatch):
    hooks()
    monkeypatch.setenv(ns.DRY_RUN_ENV, "1")
    assert ns.post_slack("hello", title="t") is True
    assert ns.post_slack("hello", title="t", route="digest") is True


def _capture_payload(monkeypatch):
    sent = {}
    real = ns._egress_scrub

    def capture(text):
        sent["text"] = text
        return real(text)
    monkeypatch.setattr(ns, "_egress_scrub", capture)
    return sent


def test_digest_fallback_gets_an_ascii_title_marker(hooks, monkeypatch):
    hooks(digest_hook=False)
    monkeypatch.setenv(ns.DRY_RUN_ENV, "1")
    sent = _capture_payload(monkeypatch)
    ns.post_slack("digest body", title="daily digest", route="digest")
    assert sent["text"].startswith("*[digest] daily digest*")


def test_no_marker_when_the_digest_channel_exists(hooks, monkeypatch):
    hooks(digest_hook=True)
    monkeypatch.setenv(ns.DRY_RUN_ENV, "1")
    sent = _capture_payload(monkeypatch)
    ns.post_slack("digest body", title="daily digest", route="digest")
    assert sent["text"].startswith("*daily digest*")


def test_unknown_route_goes_to_alerts(hooks, monkeypatch):
    hooks(digest_hook=True)
    monkeypatch.setenv(ns.DRY_RUN_ENV, "1")
    seen = {}
    real = ns._resolve_webhook

    def spy(route="alerts"):
        seen["route"] = route
        return real(route)
    monkeypatch.setattr(ns, "_resolve_webhook", spy)
    assert ns.post_slack("x", route="pagerz") is True
    assert seen["route"] == "alerts"


def test_backward_compatible_positional_call(hooks, monkeypatch):
    """Existing post_slack(text, title) callers keep working and land on alerts."""
    hooks(digest_hook=True)
    monkeypatch.setenv(ns.DRY_RUN_ENV, "1")
    sent = _capture_payload(monkeypatch)
    assert ns.post_slack("hi", "a title") is True
    assert sent["text"].startswith("*a title*")


def test_cli_dry_run_flag(hooks, capsys):
    hooks()
    assert ns.main(["--text", "hello", "--route", "digest", "--dry-run"]) == 0
    err = capsys.readouterr().err
    assert "DRY-RUN" in err and "hooks.slack.com" not in err   # the URL is a secret


def test_cli_not_configured_exits_2(hooks):
    hooks(main_hook=False)
    assert ns.main(["--text", "hello"]) == 2
