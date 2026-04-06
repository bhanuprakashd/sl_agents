# aass_agents/tools/pipeline_metrics.py
"""
Pipeline Metrics — tracks success rates, timing, and trajectory per pipeline stage.

Stores metrics in SQLite for dashboard consumption. Each pipeline run gets a
run_id, and each stage within the run gets timing + status tracking.

Usage (in tools or callbacks):
    from tools.pipeline_metrics import record_stage_start, record_stage_end, get_run_metrics

    record_stage_start(run_id, "architect_agent")
    # ... agent runs ...
    record_stage_end(run_id, "architect_agent", status="success", iterations=2)
"""
import json
import sqlite3
import time
import uuid
import logging
from pathlib import Path
from typing import Optional

_log = logging.getLogger(__name__)

METRICS_DB_PATH = Path(__file__).parent.parent / "data" / "pipeline_metrics.db"
METRICS_DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(METRICS_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_metrics_tables():
    """Create metrics tables if they don't exist."""
    conn = _get_conn()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS pipeline_runs (
                run_id         TEXT PRIMARY KEY,
                pipeline_name  TEXT NOT NULL,
                prompt         TEXT,
                status         TEXT NOT NULL DEFAULT 'running',
                started_at     REAL NOT NULL,
                ended_at       REAL,
                duration_ms    INTEGER,
                total_stages   INTEGER DEFAULT 0,
                passed_stages  INTEGER DEFAULT 0,
                failed_stages  INTEGER DEFAULT 0,
                metadata       TEXT
            );

            CREATE TABLE IF NOT EXISTS stage_metrics (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id         TEXT NOT NULL,
                stage_name     TEXT NOT NULL,
                status         TEXT NOT NULL DEFAULT 'running',
                started_at     REAL NOT NULL,
                ended_at       REAL,
                duration_ms    INTEGER,
                iterations     INTEGER DEFAULT 1,
                token_count    INTEGER,
                error_message  TEXT,
                metadata       TEXT,
                FOREIGN KEY (run_id) REFERENCES pipeline_runs(run_id)
            );

            CREATE INDEX IF NOT EXISTS idx_stage_run ON stage_metrics(run_id);
            CREATE INDEX IF NOT EXISTS idx_runs_status ON pipeline_runs(status);
            CREATE INDEX IF NOT EXISTS idx_runs_started ON pipeline_runs(started_at);
        """)
        conn.commit()
    finally:
        conn.close()


init_metrics_tables()


# ── Run-level operations ────────────────────────────────────────────────────

def start_run(pipeline_name: str, prompt: str = "", metadata: Optional[dict] = None) -> str:
    """Start tracking a new pipeline run. Returns run_id."""
    run_id = str(uuid.uuid4())
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO pipeline_runs (run_id, pipeline_name, prompt, status, started_at, metadata) "
            "VALUES (?, ?, ?, 'running', ?, ?)",
            (run_id, pipeline_name, prompt, time.time(),
             json.dumps(metadata) if metadata else None),
        )
        conn.commit()
    finally:
        conn.close()
    _log.info("Metrics: Started run %s for pipeline '%s'", run_id[:8], pipeline_name)
    return run_id


def end_run(run_id: str, status: str = "success"):
    """Mark a pipeline run as completed."""
    conn = _get_conn()
    try:
        now = time.time()
        row = conn.execute(
            "SELECT started_at FROM pipeline_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        duration_ms = int((now - row["started_at"]) * 1000) if row else 0

        stages = conn.execute(
            "SELECT status FROM stage_metrics WHERE run_id = ?", (run_id,)
        ).fetchall()
        total = len(stages)
        passed = sum(1 for s in stages if s["status"] == "success")
        failed = sum(1 for s in stages if s["status"] == "failed")

        conn.execute(
            "UPDATE pipeline_runs SET status=?, ended_at=?, duration_ms=?, "
            "total_stages=?, passed_stages=?, failed_stages=? WHERE run_id=?",
            (status, now, duration_ms, total, passed, failed, run_id),
        )
        conn.commit()
    finally:
        conn.close()
    _log.info("Metrics: Run %s ended with status '%s' (%dms)", run_id[:8], status, duration_ms)


# ── Stage-level operations ──────────────────────────────────────────────────

def record_stage_start(run_id: str, stage_name: str) -> int:
    """Record the start of a pipeline stage. Returns the stage metric ID."""
    conn = _get_conn()
    try:
        cursor = conn.execute(
            "INSERT INTO stage_metrics (run_id, stage_name, status, started_at) "
            "VALUES (?, ?, 'running', ?)",
            (run_id, stage_name, time.time()),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def record_stage_end(
    run_id: str,
    stage_name: str,
    status: str = "success",
    iterations: int = 1,
    token_count: Optional[int] = None,
    error_message: Optional[str] = None,
    metadata: Optional[dict] = None,
):
    """Record the completion of a pipeline stage."""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT id, started_at FROM stage_metrics "
            "WHERE run_id=? AND stage_name=? AND status='running' "
            "ORDER BY id DESC LIMIT 1",
            (run_id, stage_name),
        ).fetchone()

        now = time.time()
        duration_ms = int((now - row["started_at"]) * 1000) if row else 0

        if row:
            conn.execute(
                "UPDATE stage_metrics SET status=?, ended_at=?, duration_ms=?, "
                "iterations=?, token_count=?, error_message=?, metadata=? WHERE id=?",
                (status, now, duration_ms, iterations, token_count,
                 error_message, json.dumps(metadata) if metadata else None, row["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO stage_metrics "
                "(run_id, stage_name, status, started_at, ended_at, duration_ms, "
                "iterations, token_count, error_message, metadata) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (run_id, stage_name, status, now, now, 0, iterations,
                 token_count, error_message, json.dumps(metadata) if metadata else None),
            )
        conn.commit()
    finally:
        conn.close()


# ── Query operations ────────────────────────────────────────────────────────

def get_run_metrics(run_id: str) -> dict:
    """Get full metrics for a pipeline run including all stages."""
    conn = _get_conn()
    try:
        run = conn.execute(
            "SELECT * FROM pipeline_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        if not run:
            return {"error": f"Run {run_id} not found"}

        stages = conn.execute(
            "SELECT * FROM stage_metrics WHERE run_id = ? ORDER BY started_at",
            (run_id,),
        ).fetchall()

        return {
            **dict(run),
            "stages": [dict(s) for s in stages],
        }
    finally:
        conn.close()


def get_pipeline_stats(pipeline_name: Optional[str] = None, since_hours: int = 24) -> dict:
    """Aggregate pipeline statistics: success rate, avg duration, stage breakdown."""
    conn = _get_conn()
    try:
        cutoff = time.time() - (since_hours * 3600)
        where = "WHERE started_at > ?"
        params: list = [cutoff]
        if pipeline_name:
            where += " AND pipeline_name = ?"
            params.append(pipeline_name)

        runs = conn.execute(
            f"SELECT * FROM pipeline_runs {where} ORDER BY started_at DESC",
            params,
        ).fetchall()

        total = len(runs)
        if total == 0:
            return {"total_runs": 0, "success_rate": 0, "avg_duration_ms": 0, "stages": {}}

        successful = sum(1 for r in runs if r["status"] == "success")
        durations = [r["duration_ms"] for r in runs if r["duration_ms"]]
        avg_duration = sum(durations) // len(durations) if durations else 0

        # Stage-level stats
        stage_rows = conn.execute(
            "SELECT stage_name, status, duration_ms, iterations FROM stage_metrics "
            "WHERE run_id IN (SELECT run_id FROM pipeline_runs " + where + ")",
            params,
        ).fetchall()

        stage_stats: dict = {}
        for s in stage_rows:
            name = s["stage_name"]
            if name not in stage_stats:
                stage_stats[name] = {
                    "total": 0, "success": 0, "failed": 0,
                    "durations": [], "total_iterations": 0,
                }
            stats = stage_stats[name]
            stats["total"] += 1
            if s["status"] == "success":
                stats["success"] += 1
            elif s["status"] == "failed":
                stats["failed"] += 1
            if s["duration_ms"]:
                stats["durations"].append(s["duration_ms"])
            stats["total_iterations"] += s["iterations"] or 1

        # Compute averages
        for name, stats in stage_stats.items():
            d = stats.pop("durations")
            stats["avg_duration_ms"] = sum(d) // len(d) if d else 0
            stats["avg_iterations"] = round(
                stats["total_iterations"] / stats["total"], 1
            ) if stats["total"] > 0 else 0

        return {
            "total_runs": total,
            "successful_runs": successful,
            "failed_runs": total - successful,
            "success_rate": round(successful / total * 100, 1),
            "avg_duration_ms": avg_duration,
            "stages": stage_stats,
        }
    finally:
        conn.close()


def get_recent_runs(limit: int = 20) -> list[dict]:
    """Get most recent pipeline runs with their stage summaries."""
    conn = _get_conn()
    try:
        runs = conn.execute(
            "SELECT * FROM pipeline_runs ORDER BY started_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in runs]
    finally:
        conn.close()
