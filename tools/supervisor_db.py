"""
Supervisor DB — schema init and async CRUD helpers for all 5 supervisor tables.
All writes use asyncio.to_thread to avoid blocking the event loop (matches memory_store.py).
SQLite opened in WAL mode for safe concurrent access.
"""
import sqlite3
import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

SUPERVISOR_DB_PATH = Path(__file__).parent.parent / "sales_memory.db"

AGENT_TTL_DAYS: dict[str, Optional[float]] = {
    "lead_researcher": 7,
    "outreach_composer": 14,
    "sales_call_prep": 3,
    "objection_handler": None,      # per-run — never cache
    "proposal_generator": 30,
    "crm_updater": None,
    "deal_analyst": 1,
    "audience_builder": 7,
    "campaign_composer": 14,
    "content_strategist": 14,
    "seo_analyst": 30,
    "campaign_analyst": 7,
    "brand_voice": 90,
    "pm_agent": None,
    "architect_agent": float("inf"),  # manual reset only
    "devops_agent": None,
    "db_agent": None,
    "backend_builder_agent": None,
    "frontend_builder_agent": None,
    "qa_agent": None,
    "reflection_agent": None,       # meta-agent, never cached
    "company_orchestrator": None,   # router, never cached
    # ── Engineering Department ────────────────────────────────────────────────
    "engineering_orchestrator":       None,             # router, never cached
    "solutions_architect_agent":      float("inf"),     # architecture decisions: manual reset only
    "data_engineer_agent":            None,             # pipeline builds are per-run
    "ml_engineer_agent":              None,             # pipeline builds are per-run
    "systems_engineer_agent":         float("inf"),     # toolchain designs stable until changed
    "integration_engineer_agent":     None,             # integrations are per-run
    "platform_engineer_agent":        float("inf"),     # platform configs stable until changed
    "sdet_agent":                     None,             # test runs are per-run
    # ── Research & Development Department ────────────────────────────────────
    "research_orchestrator":          None,             # router, never cached
    "research_scientist_agent":       30,               # academic findings stable ~1 month
    "ml_researcher_agent":            14,               # SOTA moves fast, refresh fortnightly
    "applied_scientist_agent":        14,               # feasibility reassessed frequently
    "data_scientist_agent":           7,                # metrics and experiments change weekly
    "competitive_analyst_agent":      7,                # market landscape moves fast
    "user_researcher_agent":          30,               # user insights stable ~1 month
    "knowledge_manager_agent":        30,               # research briefs stable ~1 month
    # ── QA & Testing Department ──────────────────────────────────────────────
    "qa_orchestrator":                None,             # router, never cached
    "test_architect_agent":           float("inf"),     # test strategy stable until changed
    "test_automation_engineer_agent": None,             # test runs are per-run
    "performance_engineer_agent":     7,                # performance baselines refresh weekly
    "security_tester_agent":          7,                # security posture changes frequently
    "qa_engineer_agent":              None,             # QA runs are per-run
    "chaos_engineer_agent":           None,             # chaos experiments are per-run
    "_default": 7,                  # safety net for unlisted agents
}


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(SUPERVISOR_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_supervisor_tables() -> None:
    """Create supervisor tables if they don't exist. Safe to call multiple times."""
    with _get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS supervisor_runs (
                run_id          TEXT PRIMARY KEY,
                pipeline_type   TEXT NOT NULL,
                status          TEXT NOT NULL DEFAULT 'pending',
                current_step    INT DEFAULT 0,
                total_steps     INT,
                context_json    TEXT,
                checkpoint_json TEXT,
                created_at      TEXT NOT NULL,
                updated_at      TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS supervisor_events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id      TEXT NOT NULL,
                agent_name  TEXT NOT NULL,
                event_type  TEXT NOT NULL,
                payload_json TEXT,
                created_at  TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_sup_events_run
                ON supervisor_events(run_id);
            CREATE INDEX IF NOT EXISTS idx_sup_events_agent
                ON supervisor_events(agent_name, created_at);

            CREATE TABLE IF NOT EXISTS supervisor_circuit_breakers (
                agent_name      TEXT PRIMARY KEY,
                failure_count   INT NOT NULL DEFAULT 0,
                last_failure_at TEXT,
                opened_at       TEXT,
                state           TEXT NOT NULL DEFAULT 'closed'
            );

            CREATE TABLE IF NOT EXISTS supervisor_dlq (
                run_id               TEXT PRIMARY KEY,
                pipeline_type        TEXT,
                blocked_on           TEXT,
                last_error           TEXT,
                completed_steps_json TEXT,
                created_at           TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS supervisor_output_validity (
                entity_id   TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                agent_name  TEXT NOT NULL,
                run_id      TEXT,
                last_run_at TEXT,
                invalidated_by TEXT,
                expires_at  TEXT,
                PRIMARY KEY (entity_id, entity_type, agent_name)
            );
        """)


# ── Runs ─────────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.utcnow().isoformat()


def create_run(run_id: str, pipeline_type: str, context: dict) -> None:
    with _get_conn() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO supervisor_runs
               (run_id, pipeline_type, status, current_step, context_json, created_at, updated_at)
               VALUES (?, ?, 'pending', 0, ?, ?, ?)""",
            (run_id, pipeline_type, json.dumps(context), _now(), _now()),
        )


def update_run(run_id: str, **kwargs) -> None:
    """Update any column on supervisor_runs by name."""
    kwargs["updated_at"] = _now()
    cols = ", ".join(f"{k} = ?" for k in kwargs)
    vals = list(kwargs.values()) + [run_id]
    with _get_conn() as conn:
        conn.execute(f"UPDATE supervisor_runs SET {cols} WHERE run_id = ?", vals)


def get_run(run_id: str) -> Optional[dict]:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM supervisor_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        return dict(row) if row else None


# ── Events ───────────────────────────────────────────────────────────────────

def append_event(run_id: str, agent_name: str, event_type: str, payload: dict) -> None:
    with _get_conn() as conn:
        conn.execute(
            """INSERT INTO supervisor_events (run_id, agent_name, event_type, payload_json, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (run_id, agent_name, event_type, json.dumps(payload), _now()),
        )


def get_recent_events(run_id: str, limit: int = 10) -> list[dict]:
    with _get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM supervisor_events WHERE run_id = ?
               ORDER BY id DESC LIMIT ?""",
            (run_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]


# ── Circuit Breakers ──────────────────────────────────────────────────────────

def get_circuit(agent_name: str) -> dict:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM supervisor_circuit_breakers WHERE agent_name = ?",
            (agent_name,),
        ).fetchone()
        if row:
            return dict(row)
        return {"agent_name": agent_name, "failure_count": 0, "state": "closed",
                "last_failure_at": None, "opened_at": None}


def upsert_circuit(agent_name: str, **kwargs) -> None:
    existing = get_circuit(agent_name)
    existing.update(kwargs)
    with _get_conn() as conn:
        conn.execute(
            """INSERT INTO supervisor_circuit_breakers
               (agent_name, failure_count, last_failure_at, opened_at, state)
               VALUES (:agent_name, :failure_count, :last_failure_at, :opened_at, :state)
               ON CONFLICT(agent_name) DO UPDATE SET
                   failure_count   = excluded.failure_count,
                   last_failure_at = excluded.last_failure_at,
                   opened_at       = excluded.opened_at,
                   state           = excluded.state""",
            existing,
        )


# ── DLQ ──────────────────────────────────────────────────────────────────────

def push_dlq(run_id: str, pipeline_type: str, blocked_on: str,
             last_error: str, completed_steps: list) -> None:
    with _get_conn() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO supervisor_dlq
               (run_id, pipeline_type, blocked_on, last_error, completed_steps_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (run_id, pipeline_type, blocked_on, last_error,
             json.dumps(completed_steps), _now()),
        )


def list_dlq_entries() -> list[dict]:
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM supervisor_dlq ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


# ── Output Validity ───────────────────────────────────────────────────────────

def set_validity(entity_id: str, entity_type: str, agent_name: str,
                 run_id: str, ttl_days: Optional[float]) -> None:
    now = datetime.utcnow()
    if ttl_days is None:
        expires_at = None          # per-run — always stale
    elif ttl_days == float("inf"):
        expires_at = "9999-12-31"  # architect: manual reset only
    else:
        expires_at = (now + timedelta(days=ttl_days)).isoformat()

    with _get_conn() as conn:
        conn.execute(
            """INSERT INTO supervisor_output_validity
               (entity_id, entity_type, agent_name, run_id, last_run_at, expires_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(entity_id, entity_type, agent_name) DO UPDATE SET
                   run_id      = excluded.run_id,
                   last_run_at = excluded.last_run_at,
                   expires_at  = excluded.expires_at,
                   invalidated_by = NULL""",
            (entity_id, entity_type, agent_name, run_id, now.isoformat(), expires_at),
        )


def is_stale(entity_id: str, entity_type: str, agent_name: str) -> bool:
    """Return True if no valid cached output exists for this agent + entity."""
    with _get_conn() as conn:
        row = conn.execute(
            """SELECT expires_at, invalidated_by FROM supervisor_output_validity
               WHERE entity_id=? AND entity_type=? AND agent_name=?""",
            (entity_id, entity_type, agent_name),
        ).fetchone()

    if not row:
        return True  # never run
    if row["invalidated_by"]:
        return True  # explicitly invalidated
    if row["expires_at"] is None:
        return True  # per-run agent
    if row["expires_at"] == "9999-12-31":
        return False  # architect: never expires
    return datetime.utcnow().isoformat() > row["expires_at"]


def invalidate(entity_id: str, entity_type: str, agent_names: list[str],
               reason: str) -> None:
    with _get_conn() as conn:
        for name in agent_names:
            conn.execute(
                """UPDATE supervisor_output_validity
                   SET invalidated_by = ?
                   WHERE entity_id=? AND entity_type=? AND agent_name=?""",
                (reason, entity_id, entity_type, name),
            )
