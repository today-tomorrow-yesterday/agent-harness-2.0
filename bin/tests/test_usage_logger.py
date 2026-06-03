from skill_forge.usage_logger import build_usage_record, parse_payload


def test_parse_payload_strips_bom():
    raw = "﻿" + '{"tool_name": "Skill", "tool_input": {"skill": "x"}}'
    assert parse_payload(raw) == {"tool_name": "Skill", "tool_input": {"skill": "x"}}


def test_parse_payload_strips_misdecoded_bom():
    # UTF-8 BOM bytes decoded as latin-1: EF BB BF -> U+00EF U+00BB U+00BF
    raw = "\xef\xbb\xbf" + '{"tool_name": "Skill", "tool_input": {"skill": "x"}}'
    assert parse_payload(raw) == {"tool_name": "Skill", "tool_input": {"skill": "x"}}


def test_parse_payload_handles_empty_and_garbage():
    assert parse_payload("") == {}
    assert parse_payload("   ") == {}
    assert parse_payload("not json") == {}
    assert parse_payload("[1,2,3]") == {}   # non-dict JSON -> {}


def test_skill_payload_skill_field():
    p = {"tool_name": "Skill", "session_id": "s9", "cwd": "C:\\x",
         "tool_input": {"skill": "clone-route", "args": "now"}}
    rec = build_usage_record(p, "2026-05-30T00:00:00Z")
    assert rec == {"ts": "2026-05-30T00:00:00Z", "skill": "clone-route",
                   "args": "now", "session_id": "s9", "cwd": "C:\\x"}


def test_skill_payload_skill_name_variant():
    p = {"tool_name": "Skill", "tool_input": {"skill_name": "watch", "arguments": "v"}}
    rec = build_usage_record(p, "2026-05-30T00:00:00Z")
    assert rec["skill"] == "watch" and rec["args"] == "v"


def test_non_skill_tool_returns_none():
    assert build_usage_record({"tool_name": "Bash", "tool_input": {}}, "t") is None


def test_missing_skill_returns_none():
    assert build_usage_record({"tool_name": "Skill", "tool_input": {}}, "t") is None


def test_non_dict_returns_none():
    assert build_usage_record("not a dict", "t") is None
