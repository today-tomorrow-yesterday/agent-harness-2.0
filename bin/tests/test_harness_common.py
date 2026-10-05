"""Tests for harness_common.py — the three helpers background jobs share."""
import harness_common as hc


# --- defang_untrusted ---
def test_defang_breaks_marker_runs_but_keeps_the_text_readable():
    out = hc.defang_untrusted("before ======= after <<<<<<< end >>>>")
    assert "=======" not in out and "<<<<<<<" not in out and ">>>>" not in out
    assert "before" in out and "after" in out and "end" in out


def test_defang_tags_fence_phrases():
    for phrase in ("END UNTRUSTED WEB CONTENT", "UNTRUSTED_METADATA", "TRANSCRIPT_END"):
        assert "(defanged)" in hc.defang_untrusted(f"x {phrase} y"), phrase


def test_defang_leaves_ordinary_text_alone():
    text = "Compare a == b, then a => b. Nothing untoward here."
    assert hc.defang_untrusted(text) == text
    assert hc.defang_untrusted(None) == ""


# --- classify_claude_result ---
def test_exit_zero_is_ok_even_when_the_answer_mentions_limits():
    assert hc.classify_claude_result(0, "the API has a rate limit of 401 requests") == ("ok", None)


def test_rate_limit_is_read_from_stdout_and_carries_the_reset_hint():
    status, detail = hc.classify_claude_result(1, "You've hit your session limit. Resets 3pm", "")
    assert status == "rate_limited" and detail == "3pm"


def test_per_model_cap_is_rate_limited_not_a_generic_error():
    status, _ = hc.classify_claude_result(
        1, "You've reached your Opus limit. Switch to another model, or manage usage credits")
    assert status == "rate_limited"


def test_auth_failure_and_model_unavailable_and_plain_error():
    assert hc.classify_claude_result(1, "", "401 invalid authentication credentials")[0] == "auth_failed"
    assert hc.classify_claude_result(1, "Please run /login")[0] == "auth_failed"
    assert hc.classify_claude_result(1, "model is currently unavailable")[0] == "model_unavailable"
    assert hc.classify_claude_result(3, "something else broke") == ("error", "exit 3")


# --- clean_env ---
def test_clean_env_never_forwards_a_metered_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "x")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "subscription")
    monkeypatch.setenv("PATH_LIKE_THING", "keep")
    env = hc.clean_env(CLAUDE_BRAIN_SKIP_HOOKS="1")
    assert "ANTHROPIC_API_KEY" not in env and "ANTHROPIC_AUTH_TOKEN" not in env
    assert env["CLAUDE_CODE_OAUTH_TOKEN"] == "subscription"  # the subscription login must pass
    assert env["PATH_LIKE_THING"] == "keep"
    assert env["CLAUDE_BRAIN_SKIP_HOOKS"] == "1"
