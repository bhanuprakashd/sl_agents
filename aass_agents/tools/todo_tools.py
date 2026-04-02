"""
Todo Recency Anchoring Tools — Manus context engineering pattern.

Problem: On long agent runs (50+ tool calls), goals stated at the start of the
INSTRUCTION fall into the "lost-in-the-middle" zone where attention degrades.

Solution: Maintain a live todo list in SQLite. Calling read_todo() late in a
run re-injects the goal list into the recency window, where attention is highest.

Pattern (from Manus):
  1. write_todo(session_id, steps)     ← at run start: capture the plan
  2. read_todo(session_id)             ← before each step: re-anchor attention
  3. complete_todo_step(session_id, i) ← after each step: mark progress
"""

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional

_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "product_pipeline.db")


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_table() -> None:
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS agent_todos (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id  TEXT NOT NULL,
                steps       TEXT NOT NULL,   -- JSON list of {index, text, done, completed_at}
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            )
        """)
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_todos_session ON agent_todos(session_id)"
        )


_init_table()


# ── Tools ─────────────────────────────────────────────────────────────────────

def write_todo(session_id: str, steps: list[str]) -> str:
    """
    Write (or overwrite) the todo list for this session.
    Call this at the START of a run to capture your plan.
    Calling read_todo() later re-anchors these goals in your attention window.

    Args:
        session_id: Unique identifier for this agent run (e.g. product_id or deal_id)
        steps: Ordered list of task descriptions (e.g. ["Research company", "Draft proposal"])

    Returns:
        Confirmation string with the todo list rendered.
    """
    now = datetime.now(timezone.utc).isoformat()
    step_objects = [
        {"index": i, "text": s, "done": False, "completed_at": None}
        for i, s in enumerate(steps)
    ]
    steps_json = json.dumps(step_objects)

    with _get_conn() as conn:
        conn.execute(
            """
            INSERT INTO agent_todos (session_id, steps, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                steps      = excluded.steps,
                updated_at = excluded.updated_at
            """,
            (session_id, steps_json, now, now),
        )

    return _render_todo(session_id, step_objects)


def read_todo(session_id: str) -> str:
    """
    Read the current todo list for this session.
    Call this BEFORE EACH MAJOR STEP to re-anchor your goals in your attention
    window. This prevents the 'lost-in-the-middle' failure mode on long runs.

    Args:
        session_id: The session identifier used in write_todo()

    Returns:
        Rendered todo list showing ✓ completed and ○ pending steps, or a
        message if no todo exists for this session.
    """
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT steps FROM agent_todos WHERE session_id = ?", (session_id,)
        ).fetchone()

    if not row:
        return f"No todo list found for session '{session_id}'. Call write_todo() first."

    steps = json.loads(row["steps"])
    return _render_todo(session_id, steps)


def complete_todo_step(session_id: str, step_index: int) -> str:
    """
    Mark a todo step as completed.
    Call this AFTER completing each step so the todo list reflects current progress.

    Args:
        session_id: The session identifier used in write_todo()
        step_index: Zero-based index of the completed step

    Returns:
        Updated todo list, or error message.
    """
    now = datetime.now(timezone.utc).isoformat()

    with _get_conn() as conn:
        row = conn.execute(
            "SELECT steps FROM agent_todos WHERE session_id = ?", (session_id,)
        ).fetchone()

        if not row:
            return f"No todo list found for session '{session_id}'."

        steps = json.loads(row["steps"])

        if step_index < 0 or step_index >= len(steps):
            return f"step_index {step_index} out of range (0–{len(steps)-1})."

        steps[step_index]["done"] = True
        steps[step_index]["completed_at"] = now

        conn.execute(
            "UPDATE agent_todos SET steps = ?, updated_at = ? WHERE session_id = ?",
            (json.dumps(steps), now, session_id),
        )

    return _render_todo(session_id, steps)


def get_todo_summary(session_id: str) -> str:
    """
    Return a one-line progress summary: "3/7 steps completed".
    Useful for status checks without re-reading the full list.

    Args:
        session_id: The session identifier

    Returns:
        Progress summary string.
    """
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT steps FROM agent_todos WHERE session_id = ?", (session_id,)
        ).fetchone()

    if not row:
        return f"No todo for session '{session_id}'."

    steps = json.loads(row["steps"])
    done = sum(1 for s in steps if s["done"])
    return f"{done}/{len(steps)} steps completed"


# ── Rendering ─────────────────────────────────────────────────────────────────

def _render_todo(session_id: str, steps: list[dict]) -> str:
    done = sum(1 for s in steps if s["done"])
    lines = [f"## Todo — session: {session_id}  ({done}/{len(steps)} done)\n"]
    for s in steps:
        mark = "✓" if s["done"] else "○"
        lines.append(f"  {mark} [{s['index']}] {s['text']}")
    return "\n".join(lines)
