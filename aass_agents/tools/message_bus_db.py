"""
Message Bus DB — persistent inter-agent messaging.

Stores messages between running agents for collaborative workflows.
Agents can send questions, answers, data, and notifications to each other.
"""
import json
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from tools.supervisor_db import _get_conn


# ── Schema ──────────────────────────────────────────────────────────────────

def init_message_tables() -> None:
    """Create agent_messages table if it doesn't exist."""
    with _get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS agent_messages (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id      TEXT NOT NULL,
                from_agent  TEXT NOT NULL,
                to_agent    TEXT NOT NULL,
                msg_type    TEXT NOT NULL,
                payload     TEXT NOT NULL,
                status      TEXT NOT NULL DEFAULT 'pending',
                created_at  TEXT NOT NULL,
                read_at     TEXT,
                expires_at  TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_msg_recipient
                ON agent_messages(run_id, to_agent, status);
            CREATE INDEX IF NOT EXISTS idx_msg_run
                ON agent_messages(run_id, created_at);
        """)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── CRUD ────────────────────────────────────────────────────────────────────

def send_message(
    run_id: str,
    from_agent: str,
    to_agent: str,
    msg_type: str,
    payload: dict | str,
    ttl_seconds: int = 300,
) -> int:
    """
    Send a message to another agent.

    Args:
        run_id: Current pipeline run ID
        from_agent: Sender agent name
        to_agent: Recipient agent name
        msg_type: One of "question", "answer", "notify", "data"
        payload: Message content (dict or string)
        ttl_seconds: Time-to-live in seconds (default 5 min)

    Returns:
        Message ID
    """
    now = _now()
    expires = datetime.now(timezone.utc)
    from datetime import timedelta
    expires_at = (expires + timedelta(seconds=ttl_seconds)).isoformat()

    payload_str = json.dumps(payload) if isinstance(payload, dict) else payload

    with _get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO agent_messages
               (run_id, from_agent, to_agent, msg_type, payload, status, created_at, expires_at)
               VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)""",
            (run_id, from_agent, to_agent, msg_type, payload_str, now, expires_at),
        )
        return cur.lastrowid


def read_messages(
    run_id: str,
    agent_name: str,
    mark_read: bool = True,
) -> list[dict]:
    """
    Read all pending messages for an agent.
    Automatically expires old messages.
    """
    now = _now()

    with _get_conn() as conn:
        # Expire old messages
        conn.execute(
            """UPDATE agent_messages
               SET status = 'expired'
               WHERE status = 'pending' AND expires_at < ?""",
            (now,),
        )

        rows = conn.execute(
            """SELECT * FROM agent_messages
               WHERE run_id = ? AND to_agent = ? AND status = 'pending'
               ORDER BY created_at ASC""",
            (run_id, agent_name),
        ).fetchall()

        messages = [dict(r) for r in rows]

        if mark_read and messages:
            ids = [m["id"] for m in messages]
            placeholders = ",".join("?" * len(ids))
            conn.execute(
                f"""UPDATE agent_messages
                    SET status = 'read', read_at = ?
                    WHERE id IN ({placeholders})""",
                [now] + ids,
            )

    # Parse payload JSON
    for msg in messages:
        try:
            msg["payload"] = json.loads(msg["payload"])
        except (json.JSONDecodeError, TypeError):
            pass

    return messages


def peek_messages(run_id: str, agent_name: str) -> list[dict]:
    """Non-blocking check for pending messages (does not mark as read)."""
    return read_messages(run_id, agent_name, mark_read=False)


def get_conversation(run_id: str, agent_a: str, agent_b: str) -> list[dict]:
    """Get all messages between two agents in a run."""
    with _get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM agent_messages
               WHERE run_id = ?
               AND ((from_agent = ? AND to_agent = ?) OR (from_agent = ? AND to_agent = ?))
               ORDER BY created_at ASC""",
            (run_id, agent_a, agent_b, agent_b, agent_a),
        ).fetchall()

    messages = [dict(r) for r in rows]
    for msg in messages:
        try:
            msg["payload"] = json.loads(msg["payload"])
        except (json.JSONDecodeError, TypeError):
            pass
    return messages


def get_all_messages(run_id: str) -> list[dict]:
    """Get all messages for a run (for debugging/dashboard)."""
    with _get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM agent_messages
               WHERE run_id = ?
               ORDER BY created_at ASC""",
            (run_id,),
        ).fetchall()

    messages = [dict(r) for r in rows]
    for msg in messages:
        try:
            msg["payload"] = json.loads(msg["payload"])
        except (json.JSONDecodeError, TypeError):
            pass
    return messages


def count_pending(run_id: str, agent_name: str) -> int:
    """Count pending messages for an agent."""
    now = _now()
    with _get_conn() as conn:
        row = conn.execute(
            """SELECT COUNT(*) as cnt FROM agent_messages
               WHERE run_id = ? AND to_agent = ? AND status = 'pending'
               AND (expires_at IS NULL OR expires_at > ?)""",
            (run_id, agent_name, now),
        ).fetchone()
    return row["cnt"] if row else 0
