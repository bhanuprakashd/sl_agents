"""
SQLite-backed long-term memory store for the sales agent team.

Persists two types of memory across sessions (from RAMP paper):
  1. Deal memory    — structured deal context per company
  2. Query history  — past agent outputs for recall and deduplication
"""

import sqlite3
import json
import asyncio
from typing import Optional
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "sales_memory.db"


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db():
    with _get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS deal_memory (
                company_name    TEXT NOT NULL,
                user_id         TEXT NOT NULL DEFAULT 'default',
                deal_context    TEXT NOT NULL,   -- JSON DealContext
                updated_at      TEXT NOT NULL,
                PRIMARY KEY (company_name, user_id)
            );

            CREATE TABLE IF NOT EXISTS query_history (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                company_name    TEXT NOT NULL,
                user_id         TEXT NOT NULL DEFAULT 'default',
                agent_name      TEXT NOT NULL,
                query           TEXT NOT NULL,
                output          TEXT NOT NULL,
                created_at      TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_query_company
                ON query_history (company_name, user_id);
        """)


# Initialise on import
_init_db()


# ── Deal Memory ───────────────────────────────────────────────────────────────

async def save_deal_memory(company_name: str, deal_context: dict, user_id: str = "default") -> None:
    """Persist deal context for a company. Overwrites existing entry."""
    def _write():
        with _get_conn() as conn:
            conn.execute(
                """
                INSERT INTO deal_memory (company_name, user_id, deal_context, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(company_name, user_id) DO UPDATE SET
                    deal_context = excluded.deal_context,
                    updated_at   = excluded.updated_at
                """,
                (company_name.lower().strip(), user_id, json.dumps(deal_context), datetime.utcnow().isoformat()),
            )
    await asyncio.to_thread(_write)


async def load_deal_memory(company_name: str, user_id: str = "default") -> Optional[dict]:
    """Load persisted deal context for a company. Returns None if not found."""
    def _read():
        with _get_conn() as conn:
            row = conn.execute(
                "SELECT deal_context, updated_at FROM deal_memory WHERE company_name=? AND user_id=?",
                (company_name.lower().strip(), user_id),
            ).fetchone()
            return dict(row) if row else None

    result = await asyncio.to_thread(_read)
    if result:
        return {"deal_context": json.loads(result["deal_context"]), "updated_at": result["updated_at"]}
    return None


async def list_deals(user_id: str = "default") -> list[dict]:
    """List all companies with saved deal memory for a user."""
    def _read():
        with _get_conn() as conn:
            rows = conn.execute(
                "SELECT company_name, updated_at FROM deal_memory WHERE user_id=? ORDER BY updated_at DESC",
                (user_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    return await asyncio.to_thread(_read)


# ── Query History ─────────────────────────────────────────────────────────────

async def save_query(
    company_name: str,
    agent_name: str,
    query: str,
    output: str,
    user_id: str = "default",
) -> None:
    """Save an agent query+output to history for future recall."""
    def _write():
        with _get_conn() as conn:
            conn.execute(
                """
                INSERT INTO query_history (company_name, user_id, agent_name, query, output, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (company_name.lower().strip(), user_id, agent_name, query, output, datetime.utcnow().isoformat()),
            )

    await asyncio.to_thread(_write)


async def recall_queries(
    company_name: str,
    agent_name: Optional[str] = None,
    limit: int = 5,
    user_id: str = "default",
) -> list[dict]:
    """Recall past agent outputs for a company, optionally filtered by agent."""
    def _read():
        with _get_conn() as conn:
            if agent_name:
                rows = conn.execute(
                    """
                    SELECT agent_name, query, output, created_at FROM query_history
                    WHERE company_name=? AND user_id=? AND agent_name=?
                    ORDER BY created_at DESC LIMIT ?
                    """,
                    (company_name.lower().strip(), user_id, agent_name, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT agent_name, query, output, created_at FROM query_history
                    WHERE company_name=? AND user_id=?
                    ORDER BY created_at DESC LIMIT ?
                    """,
                    (company_name.lower().strip(), user_id, limit),
                ).fetchall()
            return [dict(r) for r in rows]

    return await asyncio.to_thread(_read)
