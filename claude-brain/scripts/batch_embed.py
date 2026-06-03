#!/usr/bin/env python3
"""
batch_embed.py - Backfill + reconcile embeddings against current model.

Phase 2 (2026-05-27): swapped from `transcript_embeddings` BLOB column to
`transcript_vec` (sqlite-vec vec0) + `transcript_vec_meta` sidecar.

This script handles TWO cases in one pass:

1. **Un-embedded eligible rows** — transcripts with `LENGTH(TRIM(content)) >= 50`
   that have no row in `transcript_vec_meta`. Mostly batch-ingested sessions
   (the live Stop-hook embeds inline; the session-start ingest does not).

2. **Model-mismatch rows** — transcripts whose `transcript_vec_meta.model`
   differs from the current `semantic_search.model` in config.yaml. After a
   model swap (e.g. MiniLM → BGE on 2026-05-25), these rows are silently
   stale until re-embedded. We re-embed them so the corpus stays coherent.

Reuses `embed_message()` from write_exchange.py so the embed logic stays in
one place. Safe to re-run; idempotent.

Usage:
    python3 scripts/batch_embed.py [--limit N] [--skip-mismatch]
"""

import argparse
import os
import sys
import time
import sqlite3
import yaml

# Suppress HuggingFace noise (must be set before any HF imports)
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TQDM_DISABLE"] = "1"
os.environ["TRANSFORMERS_VERBOSITY"] = "error"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from write_exchange import embed_message, SEMANTIC_AVAILABLE  # noqa: E402
import logging

logger = logging.getLogger("batch_embed")
logging.basicConfig(level=logging.INFO, format="%(message)s")


def load_config():
    config_path = os.path.join(ROOT, "config.yaml")
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def connect_db(db_path):
    """Connect with sqlite-vec loaded (embed_message INSERTs into transcript_vec)."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=10000;")
    try:
        import sqlite_vec
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
    except Exception as e:
        print(f"WARNING: sqlite-vec not loaded ({e}); embedding writes will fail.")
    return conn


def find_unembedded(conn):
    """Eligible (>=50-char content) rows that have NO entry in transcript_vec_meta."""
    return conn.execute("""
        SELECT t.id, t.content
        FROM transcripts t
        LEFT JOIN transcript_vec_meta tvm ON t.id = tvm.transcript_id
        WHERE tvm.transcript_id IS NULL
          AND t.content IS NOT NULL
          AND LENGTH(TRIM(t.content)) >= 50
        ORDER BY t.id
    """).fetchall()


def count_short_or_empty(conn):
    """Rows skipped because content is too short to embed (informational only)."""
    return conn.execute("""
        SELECT COUNT(*)
        FROM transcripts t
        LEFT JOIN transcript_vec_meta tvm ON t.id = tvm.transcript_id
        WHERE tvm.transcript_id IS NULL
          AND (t.content IS NULL OR LENGTH(TRIM(t.content)) < 50)
    """).fetchone()[0]


def find_mismatched(conn, current_model):
    """Rows whose meta.model != current_model (need re-embedding under the new model)."""
    return conn.execute("""
        SELECT t.id, t.content, tvm.model AS old_model
        FROM transcripts t
        JOIN transcript_vec_meta tvm ON tvm.transcript_id = t.id
        WHERE tvm.model != ?
          AND t.content IS NOT NULL
          AND LENGTH(TRIM(t.content)) >= 50
        ORDER BY t.id
    """, (current_model,)).fetchall()


def run_embed(config, conn, rows, label, batch_size=500):
    """Embed each row via write_exchange.embed_message (DELETE-then-INSERT, idempotent)."""
    total = len(rows)
    if total == 0:
        print(f"  [{label}] nothing to do.")
        return 0, 0

    print(f"  [{label}] embedding {total} rows...")
    embedded = failed = 0
    start = time.time()
    for i, row in enumerate(rows, 1):
        tid = row[0]
        content = row[1]
        try:
            embed_message(config, conn, tid, content, logger)
            embedded += 1
        except Exception as e:
            failed += 1
            if failed <= 5:
                print(f"    failed transcript {tid}: {e}")
        if i % batch_size == 0:
            conn.commit()
            elapsed = time.time() - start
            rate = i / elapsed if elapsed > 0 else 0
            remaining = (total - i) / rate if rate > 0 else 0
            print(f"    {i}/{total} ({i*100//total}%) - {rate:.0f}/s - ~{remaining:.0f}s left")
    conn.commit()
    elapsed = time.time() - start
    rate = embedded / elapsed if elapsed > 0 else 0
    print(f"    done: {embedded} embedded, {failed} failed, {elapsed:.1f}s ({rate:.0f}/s)")
    return embedded, failed


def main():
    parser = argparse.ArgumentParser(description="Backfill + reconcile transcript embeddings")
    parser.add_argument("--limit", type=int, default=None,
                        help="Cap how many rows to process this run (useful for first runs / rate-limit safety)")
    parser.add_argument("--skip-mismatch", action="store_true",
                        help="Skip the model-mismatch re-embed pass (only embed un-embedded rows)")
    args = parser.parse_args()

    if not SEMANTIC_AVAILABLE:
        print("ERROR: sentence-transformers or numpy not available.")
        sys.exit(1)

    config = load_config()
    db_path = config["storage"]["local_db_path"]
    current_model = config.get("semantic_search", {}).get("model", "BAAI/bge-base-en-v1.5")
    print(f"Current model: {current_model}")
    print(f"DB: {db_path}")

    conn = connect_db(db_path)

    # L2 fix (2026-05-27): clean up any orphan transcript_vec_meta rows whose
    # transcript_vec entry is missing (e.g., crash between DELETE and INSERT
    # in embed_message). Without this cleanup, find_unembedded would skip
    # these transcripts forever because LEFT JOIN finds a meta row.
    orphans = conn.execute("""
        DELETE FROM transcript_vec_meta
        WHERE transcript_id NOT IN (SELECT rowid FROM transcript_vec)
    """).rowcount
    if orphans:
        conn.commit()
        print(f"Cleaned {orphans} orphan transcript_vec_meta rows.")

    skip_count = count_short_or_empty(conn)
    print(f"\nSkipped (content < 50 chars): {skip_count}")

    # Pass 1: un-embedded
    unembedded = find_unembedded(conn)
    if args.limit:
        unembedded = unembedded[:args.limit]
    e1, f1 = run_embed(config, conn, unembedded, "un-embedded")

    # Pass 2: model-mismatch
    e2 = f2 = 0
    if not args.skip_mismatch:
        mismatched = find_mismatched(conn, current_model)
        if args.limit:
            remaining = max(0, args.limit - len(unembedded))
            mismatched = mismatched[:remaining]
        if mismatched:
            # Group by old model so the report explains what's being re-embedded
            from collections import Counter
            old_models = Counter(r[2] for r in mismatched)
            print(f"\nModel-mismatch rows (current={current_model}): {len(mismatched)}")
            for m, n in old_models.most_common():
                print(f"  was '{m}': {n} rows")
        e2, f2 = run_embed(config, conn, mismatched, "model-mismatch")

    conn.close()

    print(f"\nTotal: {e1 + e2} embedded, {f1 + f2} failed.")


if __name__ == "__main__":
    main()
