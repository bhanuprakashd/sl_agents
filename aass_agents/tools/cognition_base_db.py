"""
Cognition Base DB -- SQLite-backed knowledge store for the ASI-Evolve cognition base.

Tables:
  - cognition_entries : heuristics, principles, and known pitfalls per domain

All writes use asyncio.to_thread to avoid blocking the event loop.
SQLite opened in WAL mode for safe concurrent access.
"""
import sqlite3
import asyncio
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

COGNITION_DB_PATH = Path(__file__).parent.parent / "cognition_base.db"

DDL = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS cognition_entries (
    id              TEXT PRIMARY KEY,
    domain          TEXT NOT NULL,
    title           TEXT NOT NULL,
    content         TEXT NOT NULL,
    embedding       BLOB,
    source          TEXT NOT NULL,
    relevance_score REAL DEFAULT 0.0,
    created_at      TEXT NOT NULL,
    access_count    INTEGER DEFAULT 0
);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(COGNITION_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """Create all tables if they do not exist."""
    with _connect() as conn:
        conn.executescript(DDL)


async def async_init_db() -> None:
    await asyncio.to_thread(init_db)


# -- cognition_entries CRUD ----------------------------------------------------

def add_entry_sync(
    domain: str,
    title: str,
    content: str,
    embedding_bytes: Optional[bytes],
    source: str,
) -> str:
    """Insert a new cognition entry. Returns the generated id."""
    entry_id = uuid.uuid4().hex
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO cognition_entries
              (id, domain, title, content, embedding, source, relevance_score, created_at, access_count)
            VALUES (?, ?, ?, ?, ?, ?, 0.0, ?, 0)
            """,
            (entry_id, domain, title, content, embedding_bytes, source, _now_iso()),
        )
    return entry_id


async def add_entry(
    domain: str,
    title: str,
    content: str,
    embedding_bytes: Optional[bytes],
    source: str,
) -> str:
    return await asyncio.to_thread(
        add_entry_sync, domain, title, content, embedding_bytes, source
    )


def get_entry_sync(entry_id: str) -> Optional[dict]:
    """Return a single entry by id, or None."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM cognition_entries WHERE id=?",
            (entry_id,),
        ).fetchone()
    return dict(row) if row else None


async def get_entry(entry_id: str) -> Optional[dict]:
    return await asyncio.to_thread(get_entry_sync, entry_id)


def search_by_domain_sync(domain: str, limit: int = 20) -> list[dict]:
    """Return entries for a domain, ordered by relevance_score descending."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM cognition_entries
            WHERE domain=?
            ORDER BY relevance_score DESC
            LIMIT ?
            """,
            (domain, limit),
        ).fetchall()
    return [dict(r) for r in rows]


async def search_by_domain(domain: str, limit: int = 20) -> list[dict]:
    return await asyncio.to_thread(search_by_domain_sync, domain, limit)


def update_relevance_sync(entry_id: str, new_score: float) -> None:
    """Set the relevance_score for an entry."""
    with _connect() as conn:
        conn.execute(
            "UPDATE cognition_entries SET relevance_score=? WHERE id=?",
            (new_score, entry_id),
        )


async def update_relevance(entry_id: str, new_score: float) -> None:
    await asyncio.to_thread(update_relevance_sync, entry_id, new_score)


def increment_access_sync(entry_id: str) -> None:
    """Bump access_count by 1."""
    with _connect() as conn:
        conn.execute(
            "UPDATE cognition_entries SET access_count = access_count + 1 WHERE id=?",
            (entry_id,),
        )


async def increment_access(entry_id: str) -> None:
    await asyncio.to_thread(increment_access_sync, entry_id)


def delete_entry_sync(entry_id: str) -> bool:
    """Delete an entry. Returns True if a row was removed."""
    with _connect() as conn:
        cur = conn.execute(
            "DELETE FROM cognition_entries WHERE id=?",
            (entry_id,),
        )
    return cur.rowcount == 1


async def delete_entry(entry_id: str) -> bool:
    return await asyncio.to_thread(delete_entry_sync, entry_id)


def get_all_embeddings_sync(domain: Optional[str] = None) -> list[dict]:
    """Return id, domain, title, embedding for vector search. Optionally filter by domain."""
    with _connect() as conn:
        if domain:
            rows = conn.execute(
                "SELECT id, domain, title, embedding FROM cognition_entries WHERE domain=?",
                (domain,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, domain, title, embedding FROM cognition_entries"
            ).fetchall()
    return [dict(r) for r in rows]


async def get_all_embeddings(domain: Optional[str] = None) -> list[dict]:
    return await asyncio.to_thread(get_all_embeddings_sync, domain)


def count_entries_sync(domain: Optional[str] = None) -> int:
    """Count entries, optionally filtered by domain."""
    with _connect() as conn:
        if domain:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM cognition_entries WHERE domain=?",
                (domain,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM cognition_entries"
            ).fetchone()
    return row["cnt"] if row else 0


async def count_entries(domain: Optional[str] = None) -> int:
    return await asyncio.to_thread(count_entries_sync, domain)


def get_recent_entries_sync(domain: Optional[str] = None, limit: int = 10) -> list[dict]:
    """Return most recently created entries, optionally filtered by domain."""
    with _connect() as conn:
        if domain:
            rows = conn.execute(
                """
                SELECT * FROM cognition_entries
                WHERE domain=?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (domain, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM cognition_entries
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
    return [dict(r) for r in rows]


async def get_recent_entries(domain: Optional[str] = None, limit: int = 10) -> list[dict]:
    return await asyncio.to_thread(get_recent_entries_sync, domain, limit)


# Init on import
init_db()
