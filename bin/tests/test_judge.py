import pytest
from skill_forge.judge import build_judge_prompt, parse_verdict, classify_invocation


def test_prompt_includes_skill_and_window_and_rubric():
    window = [{"role": "assistant", "content": "Did the thing."},
              {"role": "user", "content": "no that's wrong"}]
    p = build_judge_prompt("clone-route", "Route inbox content.", window)
    assert "clone-route" in p
    assert "Route inbox content." in p
    assert "no that's wrong" in p
    # rubric must enumerate the four verdicts and demand a structured last line
    for v in ("helped", "hurt", "neutral", "inapplicable"):
        assert v in p
    assert "VERDICT:" in p


@pytest.mark.parametrize("text,expected", [
    ("reasoning...\nVERDICT: helped", "helped"),
    ("VERDICT: hurt", "hurt"),
    ("VERDICT:neutral", "neutral"),
    ("VERDICT: INAPPLICABLE", "inapplicable"),
    ("some prose with no verdict", "inapplicable"),  # safe default
    ("VERDICT: banana", "inapplicable"),              # unknown -> safe default
])
def test_parse_verdict(text, expected):
    assert parse_verdict(text) == expected


def test_classify_invocation_uses_injected_invoker():
    captured = {}

    def fake_invoke(prompt: str) -> str:
        captured["prompt"] = prompt
        return "looks like a correction.\nVERDICT: hurt"

    window = [{"role": "user", "content": "no that's wrong"}]
    verdict = classify_invocation("clone-route", "Route inbox.", window, invoke_fn=fake_invoke)
    assert verdict == "hurt"
    assert "clone-route" in captured["prompt"]


def test_classify_invocation_handles_invoker_failure():
    def broken_invoke(prompt: str):
        return None                      # simulates claude -p failure
    verdict = classify_invocation("x", "y", [{"role": "user", "content": "z"}],
                                  invoke_fn=broken_invoke)
    assert verdict == "inapplicable"     # never fabricate a hurt/helped on failure
