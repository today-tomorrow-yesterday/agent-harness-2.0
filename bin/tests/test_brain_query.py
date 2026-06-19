from skill_forge.brain_query import find_invocations, get_after_window


def test_finds_command_name_invocations(brain_conn):
    inv = find_invocations(brain_conn, "route-inbox", since="2026-01-01T00:00:00Z")
    sessions = sorted(i["session_id"] for i in inv)
    assert sessions == ["s1", "s2"]            # not s3 (that was 'watch')
    assert all("timestamp" in i and "id" in i for i in inv)


def test_respects_since_cutoff(brain_conn):
    inv = find_invocations(brain_conn, "route-inbox", since="2026-05-02T00:00:00Z")
    assert [i["session_id"] for i in inv] == ["s2"]   # s1 was 2026-05-01


def test_unknown_skill_returns_empty(brain_conn):
    assert find_invocations(brain_conn, "does-not-exist", since="2026-01-01T00:00:00Z") == []


def test_after_window_returns_following_messages_same_session(brain_conn):
    # invocation row id=4 (s2, 11:00); window should be the next msgs in s2
    window = get_after_window(brain_conn, session_id="s2",
                              after_timestamp="2026-05-02T11:00:00Z", limit=6)
    contents = [m["content"] for m in window]
    assert "Routed to expert alice." in contents
    assert "no that's wrong, it should go to bob" in contents
    # must not leak rows from other sessions
    assert all(m["role"] in ("user", "assistant") for m in window)


def test_after_window_limit_truncates(brain_conn):
    window = get_after_window(brain_conn, session_id="s1",
                              after_timestamp="2026-05-01T10:00:00Z", limit=1)
    assert len(window) == 1
