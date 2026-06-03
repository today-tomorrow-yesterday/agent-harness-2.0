#!/usr/bin/env python3
"""
server.py - MCP server for claude-brain.

Read-only access to the claude-brain SQLite database.
All writes are handled by hooks and scripts.

11 tool functions:
  get_profile, get_project_state, search_transcripts, get_session,
  get_recent_sessions, lookup_decision, lookup_fact, get_recent_summaries,
  search_semantic, get_status, get_schema

Registration:
  claude mcp add brain-server python3 /path/to/mcp/server.py
"""

import datetime
import os
import pathlib
import re
import signal
import sqlite3
import sys

import yaml
from mcp.server.fastmcp import FastMCP

# fuzzy_search is in scripts/ - add to path
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from scripts.fuzzy_search import fuzzy_correct

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

ROOT = str(pathlib.Path(__file__).resolve().parent.parent)

def load_config():
    config_path = os.path.join(ROOT, "config.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

CONFIG = load_config()
DB_PATH = CONFIG["storage"]["local_db_path"]

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    # Phase 2 (2026-05-27): load sqlite-vec so transcript_vec KNN queries work.
    try:
        import sqlite_vec
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
    except Exception:
        # ANN search will return empty; other tools still work.
        pass
    return conn

# Semantic search - SQLite + numpy + sqlite-vec (Phase 2, 2026-05-27)
SEMANTIC_AVAILABLE = False
CROSS_ENCODER_AVAILABLE = False
_embed_model = None
_cross_encoder = None

try:
    from sentence_transformers import SentenceTransformer, CrossEncoder
    import numpy as np
    SEMANTIC_AVAILABLE = True
    CROSS_ENCODER_AVAILABLE = True
except (ImportError, Exception):
    pass


def _get_embed_model():
    """Lazily load the SentenceTransformer model (cached in MCP server process)."""
    global _embed_model
    if _embed_model is not None:
        return _embed_model
    sem_config = CONFIG.get("semantic_search", {})
    model_name = sem_config.get("model", "BAAI/bge-base-en-v1.5")
    _embed_model = SentenceTransformer(model_name)
    return _embed_model


def _get_cross_encoder():
    """Lazily load the CrossEncoder for re-ranking. ~80 MB; downloads on first use."""
    global _cross_encoder
    if _cross_encoder is not None:
        return _cross_encoder
    if not CROSS_ENCODER_AVAILABLE:
        return None
    try:
        # ms-marco-MiniLM-L-6-v2 is the standard small re-ranker — punches above
        # its weight for hybrid-search re-ranking. ~80 MB, ~10ms per pair on CPU.
        _cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    except Exception:
        _cross_encoder = None
    return _cross_encoder


# _load_embeddings_matrix REMOVED Phase 2 (2026-05-27): the brute-force "load
# all 106 MB of BLOBs into a NumPy matrix and dot-product" path is gone.
# transcript_vec (sqlite-vec vec0, cosine distance) handles ANN natively.

mcp = FastMCP("brain-server")

# ---------------------------------------------------------------------------
# 1. get_profile
# ---------------------------------------------------------------------------

@mcp.tool()
def get_profile() -> str:
    """Returns the user's complete profile: all brain_facts and brain_preferences.
    Call this at the start of every session to load working context."""
    conn = get_db()
    try:
        facts = conn.execute(
            "SELECT category, key, value, confidence FROM brain_facts ORDER BY category, key"
        ).fetchall()
        prefs = conn.execute(
            "SELECT category, preference FROM brain_preferences ORDER BY category"
        ).fetchall()

        if not facts and not prefs:
            return "Profile is empty. No brain_facts or brain_preferences populated yet."

        lines = ["## Brain Profile", ""]
        if facts:
            lines.append("### Facts")
            current_cat = None
            for row in facts:
                if row["category"] != current_cat:
                    current_cat = row["category"]
                    lines.append(f"\n**{current_cat}**")
                conf = f" ({row['confidence']})" if row["confidence"] else ""
                lines.append(f"- {row['key']}: {row['value']}{conf}")

        if prefs:
            lines.append("\n### Preferences")
            current_cat = None
            for row in prefs:
                if row["category"] != current_cat:
                    current_cat = row["category"]
                    lines.append(f"\n**{current_cat}**")
                lines.append(f"- {row['preference']}")

        return "\n".join(lines)
    finally:
        conn.close()

# ---------------------------------------------------------------------------
# 2. get_project_state
# ---------------------------------------------------------------------------

@mcp.tool()
def get_project_state(project: str) -> str:
    """Returns recent decisions and key facts for a given project.
    Args: project - project prefix configured in config.yaml (e.g. gen, ses, av, oth)."""
    conn = get_db()
    try:
        decisions = conn.execute(
            """SELECT decision_number, description, rationale
               FROM decisions WHERE project = ?
               ORDER BY decision_number DESC LIMIT 20""",
            (project,),
        ).fetchall()

        facts = conn.execute(
            """SELECT category, key, value
               FROM facts WHERE project = ?
               ORDER BY category, key""",
            (project,),
        ).fetchall()

        if not decisions and not facts:
            return f"No decisions or facts found for project '{project}'."

        lines = [f"## Project State: {project}", ""]

        if decisions:
            lines.append("### Recent Decisions")
            for row in decisions:
                num = row["decision_number"]
                desc = row["description"]
                lines.append(f"- #{num}: {desc}")
            lines.append("")

        if facts:
            lines.append("### Key Facts")
            current_cat = None
            for row in facts:
                if row["category"] != current_cat:
                    current_cat = row["category"]
                    lines.append(f"\n**{current_cat}**")
                lines.append(f"- {row['key']}: {row['value']}")

        return "\n".join(lines)
    finally:
        conn.close()

# ---------------------------------------------------------------------------
# 3. search_transcripts
# ---------------------------------------------------------------------------

STOP_WORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "can", "may", "might", "shall", "not", "no", "yes", "ok",
    "okay", "this", "that", "it", "i", "you", "we", "they", "me", "my",
    "your", "our", "their", "and", "or", "but", "if", "then", "so", "for",
    "of", "to", "in", "on", "at", "by", "with", "from", "up", "out",
    "into", "about", "what", "how", "when", "where", "which", "who",
    "go", "just", "let", "get", "make", "know", "think", "want", "need",
    "use", "try", "see", "look", "tell", "give", "take", "come", "also",
    "now", "here", "there", "than", "more", "some", "any", "all", "each",
    "very", "much", "well", "still", "already", "please", "thanks",
    "sure", "right", "good", "new", "first", "last", "next", "other",
    "show", "list", "find", "search", "everything", "anything",
}


def _is_fts5_syntax(raw_query: str) -> bool:
    """Check if the query uses explicit FTS5 operators."""
    return any(op in raw_query for op in [" OR ", " AND ", " NOT ", '"'])


def _extract_keywords(raw_query: str) -> list[str]:
    """Extract search keywords from a natural language query."""
    words = re.findall(r'[a-zA-Z0-9]{3,}', raw_query.lower())
    keywords = [w for w in words if w not in STOP_WORDS]
    if not keywords:
        keywords = words[:5]
    return keywords[:10]


def _keywords_to_fts(keywords: list[str]) -> str:
    """Join keywords into an FTS5 OR query."""
    return " OR ".join(f'"{kw}"' for kw in keywords)


def _build_fts_query(raw_query: str) -> str:
    """Convert a natural language query to an FTS5 OR query.

    - If the user already uses FTS5 operators (OR, AND, NOT, quotes), pass through.
    - Otherwise, extract keywords, strip stop words, join with OR.
    - Escape special characters that break FTS5 (apostrophes, etc.).
    """
    if _is_fts5_syntax(raw_query):
        return raw_query.replace("'", "")

    keywords = _extract_keywords(raw_query)
    if not keywords:
        return raw_query.replace("'", "").replace('"', "")

    return _keywords_to_fts(keywords)


def _run_fts_query(conn, fts_query: str, project: str | None, limit: int,
                    recency_bias: bool) -> list:
    """Execute an FTS5 query and return rows."""
    if recency_bias:
        order = "fts.rank * (1.0 / (1.0 + julianday('now') - julianday(t.timestamp)))"
    else:
        order = "fts.rank"

    if project:
        return conn.execute(
            f"""SELECT t.session_id, t.project, t.timestamp, t.type,
                      substr(t.content, 1, 600) as preview
               FROM transcripts_fts fts
               JOIN transcripts t ON t.rowid = fts.rowid
               WHERE transcripts_fts MATCH ? AND t.project = ?
               ORDER BY {order}
               LIMIT ?""",
            (fts_query, project, limit),
        ).fetchall()
    else:
        return conn.execute(
            f"""SELECT t.session_id, t.project, t.timestamp, t.type,
                      substr(t.content, 1, 600) as preview
               FROM transcripts_fts fts
               JOIN transcripts t ON t.rowid = fts.rowid
               WHERE transcripts_fts MATCH ?
               ORDER BY {order}
               LIMIT ?""",
            (fts_query, limit),
        ).fetchall()


def _format_results(rows, header: str = "") -> str:
    """Format search result rows into a readable string."""
    lines = []
    if header:
        lines.append(header)
        lines.append("")
    lines.append(f"## Search Results ({len(rows)} matches)")
    lines.append("")
    for row in rows:
        date = row["timestamp"][:10] if row["timestamp"] else "?"
        preview = (row["preview"] or "").replace("\n", " ").strip()
        lines.append(f"- [{date}, {row['project']}, {row['type']}] {preview}")
    lines.append("")
    lines.append("Tip: For full message content, use get_session(session_id).")
    return "\n".join(lines)


def _semantic_topk(conn, query: str, project: str | None, k: int) -> list:
    """Top-K transcripts by cosine similarity, via sqlite-vec ANN (vec0).

    Phase 2 (2026-05-27): replaced the load-everything-into-NumPy brute-force
    path with a native KNN query on the transcript_vec virtual table.
    Project filtering pushes down via JOIN.

    Returns list of dicts: {transcript_id, sim, session_id, project, timestamp, type, preview}.
    """
    if not SEMANTIC_AVAILABLE:
        return []
    sem_config = CONFIG.get("semantic_search", {})
    if not sem_config.get("enabled", False):
        return []

    # Encode the query in the same way embeddings were stored.
    # vec0 with distance_metric=cosine normalizes internally — we just hand it
    # the raw float32 bytes.
    model = _get_embed_model()
    qv = model.encode(query).astype(np.float32).tobytes()

    # k must satisfy 0 < k <= len(transcript_vec); KNN docs require a literal-ish k
    # but sqlite-vec accepts parameterized k via "AND k = ?".
    try:
        if project:
            # L2 fix (2026-05-27): vec0 evaluates KNN GLOBALLY and post-filters
            # through the JOIN — so the naive `WHERE ... AND t.project = ?` form
            # can return empty even when relevant rows exist in the project.
            # Overfetch by 20x then post-filter in Python. (sqlite-vec issue #196.)
            overfetch = max(k * 20, 200)
            rows = conn.execute(
                """SELECT v.rowid AS id, v.distance,
                          t.session_id, t.project, t.timestamp, t.type,
                          substr(t.content, 1, 600) AS preview
                   FROM transcript_vec v
                   JOIN transcripts t ON t.id = v.rowid
                   WHERE v.embedding MATCH ? AND k = ?
                   ORDER BY v.distance""",
                (qv, overfetch),
            ).fetchall()
            rows = [r for r in rows if r["project"] == project][:k]
        else:
            rows = conn.execute(
                """SELECT v.rowid AS id, v.distance,
                          t.session_id, t.project, t.timestamp, t.type,
                          substr(t.content, 1, 600) AS preview
                   FROM transcript_vec v
                   JOIN transcripts t ON t.id = v.rowid
                   WHERE v.embedding MATCH ? AND k = ?
                   ORDER BY v.distance""",
                (qv, k),
            ).fetchall()
    except sqlite3.OperationalError:
        # vec0 unavailable (extension not loaded, table missing). Degrade silently.
        return []

    return [{
        "transcript_id": r["id"],
        # L2 fix (2026-05-27): vec0 cosine distance is in [0, 2]; map to a
        # [0, 1] similarity (1.0 = identical, 0.0 = opposite) for display.
        "sim": float(1.0 - r["distance"] / 2.0),
        "session_id": r["session_id"],
        "project": r["project"],
        "timestamp": r["timestamp"],
        "type": r["type"],
        "preview": r["preview"],
    } for r in rows]


def _fts_topk(conn, query: str, project: str | None, k: int, recency_bias: bool = False) -> list:
    """Top-K transcripts by FTS5 rank. Returns dicts with same shape as _semantic_topk."""
    if recency_bias:
        order = "fts.rank + (0.1 * MAX(0, julianday('now') - julianday(t.timestamp)))"
    else:
        order = "fts.rank"

    if project:
        rows = conn.execute(
            f"""SELECT t.id, t.session_id, t.project, t.timestamp, t.type,
                       substr(t.content, 1, 600) AS preview, fts.rank
                FROM transcripts_fts fts
                JOIN transcripts t ON t.rowid = fts.rowid
                WHERE transcripts_fts MATCH ? AND t.project = ?
                ORDER BY {order} LIMIT ?""",
            (query, project, k),
        ).fetchall()
    else:
        rows = conn.execute(
            f"""SELECT t.id, t.session_id, t.project, t.timestamp, t.type,
                       substr(t.content, 1, 600) AS preview, fts.rank
                FROM transcripts_fts fts
                JOIN transcripts t ON t.rowid = fts.rowid
                WHERE transcripts_fts MATCH ?
                ORDER BY {order} LIMIT ?""",
            (query, k),
        ).fetchall()

    return [{
        "transcript_id": r["id"],
        "fts_rank": r["rank"],
        "session_id": r["session_id"],
        "project": r["project"],
        "timestamp": r["timestamp"],
        "type": r["type"],
        "preview": r["preview"],
    } for r in rows]


def _rrf_fuse(fts_results: list, sem_results: list, rrf_k: int = 60) -> list:
    """Reciprocal Rank Fusion. Score = sum over methods of 1 / (rrf_k + rank).

    Higher score = better. rrf_k=60 is the standard from the RRF paper —
    flat enough that being in two result sets always beats being in one,
    even at rank 50 vs rank 1.
    """
    scores: dict = {}
    meta: dict = {}

    for rank, r in enumerate(fts_results, start=1):
        tid = r["transcript_id"]
        scores[tid] = scores.get(tid, 0.0) + 1.0 / (rrf_k + rank)
        meta[tid] = r  # FTS row carries the same metadata we need

    for rank, r in enumerate(sem_results, start=1):
        tid = r["transcript_id"]
        scores[tid] = scores.get(tid, 0.0) + 1.0 / (rrf_k + rank)
        if tid not in meta:
            meta[tid] = r

    fused = []
    for tid, s in sorted(scores.items(), key=lambda x: -x[1]):
        row = dict(meta[tid])
        row["rrf_score"] = s
        fused.append(row)
    return fused


def _cross_encode_rerank(query: str, candidates: list, top_n: int = 20) -> list:
    """Re-rank candidates with a cross-encoder. Returns top_n sorted by re-rank score.

    Falls back to identity (preserve fused order) if cross-encoder is unavailable.
    Cost: ~10ms per (query, candidate) pair on CPU; bounded by top_n input size.
    """
    if not candidates:
        return candidates
    ce = _get_cross_encoder()
    if ce is None:
        return candidates[:top_n]

    pairs = [(query, (c.get("preview") or "")[:512]) for c in candidates]
    try:
        scores = ce.predict(pairs)
    except Exception:
        return candidates[:top_n]

    for c, s in zip(candidates, scores):
        c["ce_score"] = float(s)
    candidates.sort(key=lambda c: c.get("ce_score", 0.0), reverse=True)
    return candidates[:top_n]


@mcp.tool()
def search_transcripts(
    query: str,
    project: str | None = None,
    recency_bias: bool = False,
    mode: str = "hybrid",
) -> str:
    """Search across all conversation transcripts.

    Defaults to hybrid mode: FTS5 + semantic search fused via Reciprocal Rank
    Fusion (RRF), then re-ranked with a cross-encoder for relevance. Returns
    up to 20 results.

    Args:
      query - natural language search query (or FTS5 syntax with OR/AND/NOT/quotes)
      project - filter by project prefix (optional)
      recency_bias - if true, weight newer FTS results higher (default false)
      mode - "hybrid" (default, best quality), "fts" (FTS5-only, fastest),
             or "semantic" (embedding-only, conceptual matches)
    """
    limit = 20
    conn = get_db()
    try:
        # FTS5 syntax passthrough: explicit query mode, skip fuzzy/hybrid
        if _is_fts5_syntax(query):
            fts_query = query.replace("'", "")
            rows = _run_fts_query(conn, fts_query, project, limit, recency_bias)
            return _format_results(rows) if rows else f"No results for '{query}'."

        # Natural language: extract keywords, fuzzy-correct against vocab
        keywords = _extract_keywords(query)
        if not keywords:
            return f"No results for '{query}'."
        corrected, corrections = fuzzy_correct(keywords, DB_PATH)
        fts_query = _keywords_to_fts(corrected)

        correction_note = ""
        if corrections:
            parts = [f"'{o}' -> '{f}'" for o, f in corrections.items()]
            correction_note = f"**Did you mean:** {', '.join(parts)}"

        # FTS-only and semantic-only modes go straight to their backend
        if mode == "fts":
            rows = _run_fts_query(conn, fts_query, project, limit, recency_bias)
            if not rows:
                return f"No results for '{query}'."
            return _format_results(rows, header=correction_note)

        if mode == "semantic":
            sem = _semantic_topk(conn, query, project, limit)
            if not sem:
                return f"No semantic results for '{query}' (embeddings empty or model unavailable)."
            return _format_hybrid(sem, header="## Semantic Search Results", include_scores=True)

        # Hybrid: FTS + semantic + RRF + cross-encoder rerank
        fts_results = _fts_topk(conn, fts_query, project, k=50, recency_bias=recency_bias)
        sem_results = _semantic_topk(conn, query, project, k=50)

        if not fts_results and not sem_results:
            return f"No results for '{query}'."

        fused = _rrf_fuse(fts_results, sem_results, rrf_k=60)
        # Re-rank top-30 with cross-encoder, return top-20
        ranked = _cross_encode_rerank(query, fused[:30], top_n=limit)

        header_parts = []
        if correction_note:
            header_parts.append(correction_note)
        header_parts.append(
            f"## Hybrid Search Results "
            f"({len(ranked)} of {len(fused)} fused, "
            f"{len(fts_results)} FTS + {len(sem_results)} semantic)"
        )
        header = "\n\n".join(header_parts)

        return _format_hybrid(ranked, header=header, include_scores=True)
    finally:
        conn.close()


def _format_hybrid(rows: list, header: str = "", include_scores: bool = False) -> str:
    """Format hybrid/semantic result rows (dict-shaped, not sqlite Row)."""
    lines = []
    if header:
        lines.append(header)
        lines.append("")
    for r in rows:
        date = (r.get("timestamp") or "?")[:10]
        proj = r.get("project") or "?"
        type_ = r.get("type") or "?"
        preview = (r.get("preview") or "").replace("\n", " ").strip()
        score_parts = []
        if include_scores:
            if "ce_score" in r: score_parts.append(f"ce={r['ce_score']:.2f}")
            if "rrf_score" in r: score_parts.append(f"rrf={r['rrf_score']:.3f}")
            if "sim" in r: score_parts.append(f"sim={r['sim']:.2f}")
        score_str = f" [{' '.join(score_parts)}]" if score_parts else ""
        lines.append(f"- [{date}, {proj}, {type_}]{score_str} {preview}")
    lines.append("")
    lines.append("Tip: For full message content, use get_session(session_id).")
    return "\n".join(lines)

# ---------------------------------------------------------------------------
# 4. get_session
# ---------------------------------------------------------------------------

@mcp.tool()
def get_session(session_id: str, limit: int = 200, offset: int = 0) -> str:
    """Returns a window of the session transcript, ordered ascending by timestamp.

    Capped (default 200 msgs, max 1000) so a long session can't blow the
    context window. Pass `offset` to page further into the session.

    Args:
      session_id - the session UUID
      limit  - max messages to return (default 200, hard cap 1000)
      offset - skip this many messages from the start (default 0)
    """
    conn = get_db()
    try:
        total = conn.execute(
            "SELECT COUNT(*) FROM transcripts WHERE session_id = ?", (session_id,)
        ).fetchone()[0]

        if total == 0:
            return f"Session not found: {session_id}"

        # Clamp params
        limit = max(1, min(int(limit), 1000))
        offset = max(0, int(offset))

        rows = conn.execute(
            """SELECT type, role, content, timestamp, model
               FROM transcripts WHERE session_id = ?
               ORDER BY timestamp, id
               LIMIT ? OFFSET ?""",
            (session_id, limit, offset),
        ).fetchall()

        session = conn.execute(
            "SELECT project, started_at, ended_at, model FROM sys_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()

        end_index = offset + len(rows)
        truncated = end_index < total

        lines = [f"## Session: {session_id[:12]}..."]
        if session:
            lines.append(f"Project: {session['project']} | Model: {session['model'] or '?'}")
            lines.append(f"Time: {session['started_at'] or '?'} to {session['ended_at'] or '?'}")
        lines.append(f"Messages: {len(rows)} of {total} (showing {offset}–{end_index})")
        if truncated:
            lines.append(
                f"TRUNCATED — call get_session(session_id=\"{session_id}\", "
                f"offset={end_index}, limit={limit}) to continue."
            )
        lines.append("")

        for row in rows:
            role = row["role"] or row["type"]
            content = (row["content"] or "").strip()
            if content:
                lines.append(f"**[{role}]** {content[:500]}")
                if len(content) > 500:
                    lines.append(f"  ... ({len(content)} chars total)")
                lines.append("")

        return "\n".join(lines)
    finally:
        conn.close()

# ---------------------------------------------------------------------------
# 5. get_recent_sessions
# ---------------------------------------------------------------------------

@mcp.tool()
def get_recent_sessions(project: str | None = None, count: int = 10) -> str:
    """Lists recent sessions with metadata.
    Args: project - filter by prefix (optional), count - max sessions (default 10)."""
    conn = get_db()
    try:
        if project:
            rows = conn.execute(
                """SELECT session_id, project, started_at, ended_at, model, message_count
                   FROM sys_sessions WHERE project = ?
                   ORDER BY started_at DESC LIMIT ?""",
                (project, count),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT session_id, project, started_at, ended_at, model, message_count
                   FROM sys_sessions
                   ORDER BY started_at DESC LIMIT ?""",
                (count,),
            ).fetchall()

        if not rows:
            return "No sessions found."

        lines = [f"## Recent Sessions ({len(rows)})", ""]
        for row in rows:
            sid = row["session_id"][:12]
            date = row["started_at"][:10] if row["started_at"] else "?"
            msgs = row["message_count"] or 0
            model = row["model"] or "?"
            lines.append(f"- [{date}] {sid}... | {row['project']} | {msgs} msgs | {model}")

        return "\n".join(lines)
    finally:
        conn.close()

# ---------------------------------------------------------------------------
# 6. lookup_decision
# ---------------------------------------------------------------------------

@mcp.tool()
def lookup_decision(project: str, topic: str) -> str:
    """Finds decisions by keyword search. Recency bias is always OFF for decisions.
    Args: project - project prefix, topic - keyword to search."""
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT decision_number, description, rationale
               FROM decisions
               WHERE project = ? AND (
                   description LIKE ? OR rationale LIKE ?
               )
               ORDER BY decision_number""",
            (project, f"%{topic}%", f"%{topic}%"),
        ).fetchall()

        if not rows:
            return f"No decisions found for '{topic}' in project '{project}'."

        lines = [f"## Decisions matching '{topic}' ({len(rows)})", ""]
        for row in rows:
            lines.append(f"### Decision #{row['decision_number']}")
            lines.append(f"**Description:** {row['description']}")
            if row["rationale"]:
                lines.append(f"**Rationale:** {row['rationale']}")
            lines.append("")

        return "\n".join(lines)
    finally:
        conn.close()

# ---------------------------------------------------------------------------
# 7. lookup_fact
# ---------------------------------------------------------------------------

@mcp.tool()
def lookup_fact(
    project: str,
    category: str | None = None,
    key: str | None = None,
) -> str:
    """Finds project-specific facts by category and/or key.
    Args: project - project prefix, category - filter (character, location, etc.),
    key - specific fact key."""
    conn = get_db()
    try:
        conditions = ["project = ?"]
        params: list = [project]

        if category:
            conditions.append("category = ?")
            params.append(category)
        if key:
            conditions.append("(key LIKE ? OR value LIKE ?)")
            params.extend([f"%{key}%", f"%{key}%"])

        where = " AND ".join(conditions)
        order = "category, key"

        rows = conn.execute(
            f"""SELECT category, key, value, source
                FROM facts WHERE {where}
                ORDER BY {order}""",
            params,
        ).fetchall()

        if not rows:
            return f"No facts found for project '{project}'" + (
                f", category '{category}'" if category else ""
            ) + (f", key '{key}'" if key else "") + "."

        lines = [f"## Facts ({len(rows)})", ""]
        current_cat = None
        for row in rows:
            if row["category"] != current_cat:
                current_cat = row["category"]
                lines.append(f"**{current_cat}**")
            source = f" (source: {row['source']})" if row["source"] else ""
            lines.append(f"- {row['key']}: {row['value']}{source}")

        return "\n".join(lines)
    finally:
        conn.close()

# ---------------------------------------------------------------------------
# 8. get_recent_summaries
# ---------------------------------------------------------------------------

@mcp.tool()
def get_recent_summaries(project: str | None = None, count: int = 5) -> str:
    """Returns the last N session notes for fast context loading.
    Args: project - filter by prefix (optional), count - max notes (default 5)."""
    conn = get_db()
    try:
        if project:
            rows = conn.execute(
                """SELECT session_id, project, notes, started_at
                   FROM sys_sessions
                   WHERE project = ? AND notes IS NOT NULL AND notes != ''
                   ORDER BY started_at DESC LIMIT ?""",
                (project, count),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT session_id, project, notes, started_at
                   FROM sys_sessions
                   WHERE notes IS NOT NULL AND notes != ''
                   ORDER BY started_at DESC LIMIT ?""",
                (count,),
            ).fetchall()

        if not rows:
            return "No session notes found."

        lines = [f"## Session Notes ({len(rows)})", ""]
        for row in rows:
            date = row["started_at"][:10] if row["started_at"] else "?"
            lines.append(f"### [{date}] {row['project']} - {row['session_id'][:12]}...")
            lines.append(row["notes"] or "(empty)")
            lines.append("")

        return "\n".join(lines)
    finally:
        conn.close()

# ---------------------------------------------------------------------------
# 9. search_semantic
# ---------------------------------------------------------------------------

@mcp.tool()
def search_semantic(
    query: str,
    project: str | None = None,
    limit: int = 10,
) -> str:
    """Searches by meaning using vector embeddings (SQLite + numpy).
    Example: 'prompt caching' finds 'reduced token cost with cache_control'.
    Args: query - natural language query, project - filter (optional), limit - max results."""
    sem_config = CONFIG.get("semantic_search", {})
    if not sem_config.get("enabled", False):
        return "Semantic search is not enabled. Set semantic_search.enabled=true in config.yaml."

    if not SEMANTIC_AVAILABLE:
        return "Semantic search is unavailable (sentence-transformers or numpy not installed)."

    try:
        conn = get_db()
        try:
            results = _semantic_topk(conn, query, project, limit)
            if not results:
                proj_note = f" for project '{project}'" if project else ""
                return f"No embeddings found{proj_note}. Run batch embedding first."
            return _format_hybrid(results,
                                   header=f"## Semantic Search Results ({len(results)})",
                                   include_scores=True)
        finally:
            conn.close()
    except Exception as e:
        return f"Semantic search error: {e}"

# ---------------------------------------------------------------------------
# 10. get_status
# ---------------------------------------------------------------------------

@mcp.tool()
def get_status() -> str:
    """Returns database stats: sessions, messages, DB size, backup info, semantic status."""
    conn = get_db()
    try:
        sessions = conn.execute("SELECT COUNT(*) as c FROM sys_sessions").fetchone()["c"]
        messages = conn.execute("SELECT COUNT(*) as c FROM transcripts").fetchone()["c"]
        tool_results = conn.execute("SELECT COUNT(*) as c FROM tool_results").fetchone()["c"]
        notes_count = conn.execute(
            "SELECT COUNT(*) as c FROM sys_sessions WHERE notes IS NOT NULL AND notes != ''"
        ).fetchone()["c"]
        ingest_files = conn.execute("SELECT COUNT(*) as c FROM sys_ingest_log").fetchone()["c"]

        # Per-project breakdown
        project_rows = conn.execute(
            """SELECT s.project,
                      COUNT(DISTINCT s.session_id) as sessions,
                      COALESCE(SUM(s.message_count), 0) as messages,
                      MAX(s.started_at) as last_session
               FROM sys_sessions s
               GROUP BY s.project
               ORDER BY messages DESC"""
        ).fetchall()

        # DB size
        db_size_kb = os.path.getsize(DB_PATH) / 1024 if os.path.exists(DB_PATH) else 0

        # Backup info
        backup_dir = os.path.join(ROOT, "db-backup")
        bak1 = os.path.join(backup_dir, "claude-brain.db.bak1")
        if os.path.exists(bak1):
            bak_mtime = datetime.datetime.fromtimestamp(
                os.path.getmtime(bak1), tz=datetime.timezone.utc
            ).strftime("%Y-%m-%dT%H:%M:%SZ")
            bak_size = os.path.getsize(bak1) / 1024
            backup_info = f"{bak_mtime} ({bak_size:.0f} KB)"
        else:
            backup_info = "No backup found"

        # Semantic status
        sem_config = CONFIG.get("semantic_search", {})
        sem_enabled = sem_config.get("enabled", False)
        # Phase 2 (2026-05-27): embeddings live in transcript_vec / transcript_vec_meta now.
        embeddings = conn.execute("SELECT COUNT(*) as c FROM transcript_vec_meta").fetchone()["c"]
        sem_status = "enabled" if sem_enabled else "disabled"
        if sem_enabled and not SEMANTIC_AVAILABLE:
            sem_status += " (unavailable - sentence-transformers not installed)"
        sem_status += f" ({embeddings} embeddings)"

        lines = [
            "## Claude Brain Status",
            "",
            f"Database: {DB_PATH} ({db_size_kb:.0f} KB)",
            f"Sessions: {sessions}",
            f"Messages: {messages}",
            f"Tool results: {tool_results}",
            f"Session notes: {notes_count}",
            f"Ingested files: {ingest_files}",
            "",
            "### By Project",
        ]
        for row in project_rows:
            date = row["last_session"][:10] if row["last_session"] else "?"
            lines.append(f"- {row['project']}: {row['sessions']} sessions, {row['messages']} msgs, last: {date}")

        lines.extend([
            "",
            f"Last backup: {backup_info}",
            f"Semantic search: {sem_status}",
        ])

        return "\n".join(lines)
    finally:
        conn.close()

# ---------------------------------------------------------------------------
# 11. get_schema
# ---------------------------------------------------------------------------

@mcp.tool()
def get_schema() -> str:
    """Returns the database schema: all tables, columns, and types.
    Use this to understand the DB structure without reading documentation."""
    conn = get_db()
    try:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()

        lines = ["## Database Schema", ""]
        for tbl in tables:
            name = tbl["name"]
            cols = conn.execute(f"PRAGMA table_info(\"{name}\")").fetchall()
            col_strs = []
            for col in cols:
                pk = " PK" if col["pk"] else ""
                notnull = " NOT NULL" if col["notnull"] else ""
                default = f" DEFAULT {col['dflt_value']}" if col["dflt_value"] else ""
                col_strs.append(f"  - {col['name']} ({col['type']}{pk}{notnull}{default})")
            lines.append(f"### {name}")
            lines.extend(col_strs)

            # Show row count
            try:
                count = conn.execute(f"SELECT COUNT(*) as c FROM \"{name}\"").fetchone()["c"]
                lines.append(f"  ({count} rows)")
            except Exception:
                pass
            lines.append("")

        # Also show indexes
        indexes = conn.execute(
            "SELECT name, tbl_name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%' ORDER BY tbl_name, name"
        ).fetchall()
        if indexes:
            lines.append("### Indexes")
            for idx in indexes:
                lines.append(f"  - {idx['name']} on {idx['tbl_name']}")

        return "\n".join(lines)
    finally:
        conn.close()

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    signal.signal(signal.SIGINT, lambda *_: os._exit(0))
    mcp.run()
