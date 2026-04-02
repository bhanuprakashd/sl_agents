"""
Cost Tracker DB — per-agent token and USD cost tracking.

Records token usage (input, output, cache read/write) and computes USD cost
for every agent invocation. Queryable by run, agent, department, and time range.

Uses the same sales_memory.db as supervisor_db for colocation.
"""
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from tools.supervisor_db import SUPERVISOR_DB_PATH, _get_conn as _sup_conn


# ── Cost rates per million tokens (USD) ─────────────────────────────────────
# Keyed by model-id prefix. Falls back to "_default".
COST_PER_MILLION: dict[str, dict[str, float]] = {
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40, "cache_read": 0.025},
    "gemini-2.5-pro":   {"input": 1.25, "output": 10.0, "cache_read": 0.315},
    "gemini-2.5-flash": {"input": 0.15, "output": 0.60, "cache_read": 0.0375},
    "gpt-4o":           {"input": 2.50, "output": 10.0, "cache_read": 1.25},
    "gpt-4o-mini":      {"input": 0.15, "output": 0.60, "cache_read": 0.075},
    "claude-sonnet":    {"input": 3.00, "output": 15.0, "cache_read": 0.30},
    "claude-opus":      {"input": 15.0, "output": 75.0, "cache_read": 1.50},
    "claude-haiku":     {"input": 0.25, "output": 1.25, "cache_read": 0.03},
    "deepseek":         {"input": 0.14, "output": 0.28, "cache_read": 0.014},
    "qwen":             {"input": 0.50, "output": 2.00, "cache_read": 0.125},
    "_default":         {"input": 0.50, "output": 2.00, "cache_read": 0.125},
}


def _get_rates(model_id: str) -> dict[str, float]:
    """Match model_id to the best cost rate entry."""
    lower = model_id.lower()
    for prefix, rates in COST_PER_MILLION.items():
        if prefix != "_default" and prefix in lower:
            return rates
    return COST_PER_MILLION["_default"]


def _compute_cost(
    model_id: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
) -> float:
    """Compute USD cost from token counts."""
    rates = _get_rates(model_id)
    cost = (
        (input_tokens / 1_000_000) * rates["input"]
        + (output_tokens / 1_000_000) * rates["output"]
        + (cache_read_tokens / 1_000_000) * rates["cache_read"]
    )
    return round(cost, 8)


# ── Schema ──────────────────────────────────────────────────────────────────

def init_cost_tables() -> None:
    """Create cost_events table if it doesn't exist."""
    with _sup_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS cost_events (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id             TEXT NOT NULL,
                agent_name         TEXT NOT NULL,
                model_id           TEXT NOT NULL,
                tier               TEXT NOT NULL,
                input_tokens       INTEGER NOT NULL DEFAULT 0,
                output_tokens      INTEGER NOT NULL DEFAULT 0,
                cache_read_tokens  INTEGER NOT NULL DEFAULT 0,
                cache_write_tokens INTEGER NOT NULL DEFAULT 0,
                cost_usd           REAL NOT NULL DEFAULT 0.0,
                duration_ms        INTEGER NOT NULL DEFAULT 0,
                created_at         TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_cost_run
                ON cost_events(run_id);
            CREATE INDEX IF NOT EXISTS idx_cost_agent
                ON cost_events(agent_name, created_at);
            CREATE INDEX IF NOT EXISTS idx_cost_created
                ON cost_events(created_at);
        """)


# ── CRUD ────────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def record_cost_event(
    run_id: str,
    agent_name: str,
    model_id: str,
    tier: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    duration_ms: int = 0,
) -> None:
    """Record a single cost event from a model completion."""
    cost = _compute_cost(model_id, input_tokens, output_tokens, cache_read_tokens)
    with _sup_conn() as conn:
        conn.execute(
            """INSERT INTO cost_events
               (run_id, agent_name, model_id, tier,
                input_tokens, output_tokens, cache_read_tokens, cache_write_tokens,
                cost_usd, duration_ms, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (run_id, agent_name, model_id, tier,
             input_tokens, output_tokens, cache_read_tokens, cache_write_tokens,
             cost, duration_ms, _now()),
        )


def get_costs_by_run(run_id: str) -> list[dict]:
    """All cost events for a specific run."""
    with _sup_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM cost_events WHERE run_id = ? ORDER BY created_at",
            (run_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_costs_by_agent(agent_name: str, since: Optional[str] = None) -> list[dict]:
    """Cost events for a specific agent, optionally filtered by date."""
    query = "SELECT * FROM cost_events WHERE agent_name = ?"
    params: list = [agent_name]
    if since:
        query += " AND created_at >= ?"
        params.append(since)
    query += " ORDER BY created_at DESC"
    with _sup_conn() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def get_cost_summary(since: Optional[str] = None) -> dict:
    """Aggregate cost summary across all agents."""
    where = "WHERE created_at >= ?" if since else ""
    params: list = [since] if since else []

    with _sup_conn() as conn:
        row = conn.execute(
            f"""SELECT
                COUNT(*) as total_calls,
                COALESCE(SUM(input_tokens), 0) as total_input_tokens,
                COALESCE(SUM(output_tokens), 0) as total_output_tokens,
                COALESCE(SUM(cache_read_tokens), 0) as total_cache_read_tokens,
                COALESCE(SUM(cost_usd), 0) as total_cost_usd
            FROM cost_events {where}""",
            params,
        ).fetchone()

        by_tier = conn.execute(
            f"""SELECT tier,
                COUNT(*) as calls,
                COALESCE(SUM(input_tokens), 0) as input_tokens,
                COALESCE(SUM(output_tokens), 0) as output_tokens,
                COALESCE(SUM(cost_usd), 0) as cost_usd
            FROM cost_events {where}
            GROUP BY tier""",
            params,
        ).fetchall()

        by_agent = conn.execute(
            f"""SELECT agent_name,
                COUNT(*) as calls,
                COALESCE(SUM(input_tokens + output_tokens), 0) as total_tokens,
                COALESCE(SUM(cost_usd), 0) as cost_usd
            FROM cost_events {where}
            GROUP BY agent_name
            ORDER BY cost_usd DESC""",
            params,
        ).fetchall()

    return {
        "total_calls": row["total_calls"],
        "total_input_tokens": row["total_input_tokens"],
        "total_output_tokens": row["total_output_tokens"],
        "total_cache_read_tokens": row["total_cache_read_tokens"],
        "total_cost_usd": round(row["total_cost_usd"], 6),
        "by_tier": [dict(r) for r in by_tier],
        "by_agent": [dict(r) for r in by_agent],
    }


def get_costs_by_department(department: str, agent_department_map: dict[str, str],
                            since: Optional[str] = None) -> dict:
    """Aggregate costs for all agents in a department."""
    agents_in_dept = [
        name for name, dept in agent_department_map.items()
        if dept == department
    ]
    if not agents_in_dept:
        return {"department": department, "total_cost_usd": 0, "agents": []}

    placeholders = ",".join("?" * len(agents_in_dept))
    where = f"WHERE agent_name IN ({placeholders})"
    params: list = list(agents_in_dept)
    if since:
        where += " AND created_at >= ?"
        params.append(since)

    with _sup_conn() as conn:
        by_agent = conn.execute(
            f"""SELECT agent_name,
                COUNT(*) as calls,
                COALESCE(SUM(input_tokens + output_tokens), 0) as total_tokens,
                COALESCE(SUM(cost_usd), 0) as cost_usd
            FROM cost_events {where}
            GROUP BY agent_name
            ORDER BY cost_usd DESC""",
            params,
        ).fetchall()

    agents = [dict(r) for r in by_agent]
    total = sum(a["cost_usd"] for a in agents)
    return {
        "department": department,
        "total_cost_usd": round(total, 6),
        "agents": agents,
    }
