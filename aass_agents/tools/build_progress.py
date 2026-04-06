"""
Build Progress Tracking — real-time visibility into multi-phase builds.

Logs build phase status (starting/running/completed/failed) to SQLite.
The API layer can poll this or stream via SSE to the dashboard Monitor view.

Tables:
  build_progress: per-phase status with timestamps and output previews
"""

import json
import os
import sqlite3
from datetime import datetime, timezone

_DEFAULT_DB = os.path.join(os.path.dirname(__file__), "..", "product_pipeline.db")


def _db_path() -> str:
    return os.environ.get("PRODUCT_DB_PATH", _DEFAULT_DB)


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def _init_progress_table() -> None:
    """Create build_progress table if it doesn't exist."""
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS build_progress (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id  TEXT NOT NULL,
                phase       TEXT NOT NULL,
                status      TEXT NOT NULL DEFAULT 'starting',
                message     TEXT,
                output_preview TEXT,
                started_at  TEXT,
                completed_at TEXT,
                duration_s  REAL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_build_progress_product
            ON build_progress(product_id)
        """)


def log_build_phase(
    product_id: str,
    phase: str,
    status: str,
    message: str = "",
    output_preview: str = "",
    backend: str = "",
) -> str:
    """
    Log a build phase status update.

    Args:
        product_id: UUID of the product being built
        phase: Phase name ("scaffold", "features", "polish", "qa_test", "fix_1", "fix_2", "fix_3", "server_start")
        status: One of "starting", "running", "completed", "failed", "skipped"
        message: Human-readable status message
        output_preview: First ~500 chars of output (for debugging)
        backend: Which coding CLI is running this phase ("claude", "opencode", "")

    Returns:
        Confirmation message
    """
    _init_progress_table()
    now = datetime.now(timezone.utc).isoformat()

    # Truncate output preview
    if len(output_preview) > 500:
        output_preview = output_preview[:500] + "..."

    with _conn() as conn:
        if status == "starting":
            conn.execute("""
                INSERT INTO build_progress
                (product_id, phase, status, message, started_at)
                VALUES (?, ?, ?, ?, ?)
            """, (product_id, phase, status, message, now))
        elif status in ("completed", "failed", "skipped"):
            # Update existing row for this phase
            existing = conn.execute("""
                SELECT id, started_at FROM build_progress
                WHERE product_id = ? AND phase = ?
                ORDER BY id DESC LIMIT 1
            """, (product_id, phase)).fetchone()

            if existing:
                started = existing["started_at"] or now
                try:
                    start_dt = datetime.fromisoformat(started)
                    end_dt = datetime.fromisoformat(now)
                    duration = (end_dt - start_dt).total_seconds()
                except (ValueError, TypeError):
                    duration = 0.0

                conn.execute("""
                    UPDATE build_progress
                    SET status = ?, message = ?, output_preview = ?,
                        completed_at = ?, duration_s = ?
                    WHERE id = ?
                """, (status, message, output_preview, now, duration, existing["id"]))
            else:
                conn.execute("""
                    INSERT INTO build_progress
                    (product_id, phase, status, message, output_preview, started_at, completed_at, duration_s)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 0)
                """, (product_id, phase, status, message, output_preview, now, now))
        else:
            # "running" — update message on existing row
            conn.execute("""
                UPDATE build_progress
                SET status = ?, message = ?
                WHERE product_id = ? AND phase = ?
                AND id = (SELECT MAX(id) FROM build_progress WHERE product_id = ? AND phase = ?)
            """, (status, message, product_id, phase, product_id, phase))

    # Broadcast to SSE subscribers (push-based, replaces polling)
    try:
        from tools.progress_callbacks import broadcaster
        broadcaster.emit_sync(
            product_id=product_id,
            phase=phase,
            status=status,
            message=message,
            output_preview=output_preview,
            event_type="build.phase",
        )
    except Exception:
        pass  # Broadcast failure should not break build tracking

    return f"Build progress: {phase} → {status}"


def get_build_progress(product_id: str) -> str:
    """
    Get all build phase progress for a product.

    Args:
        product_id: UUID of the product

    Returns:
        JSON string with list of phases and their statuses
    """
    _init_progress_table()
    with _conn() as conn:
        rows = conn.execute("""
            SELECT phase, status, message, output_preview,
                   started_at, completed_at, duration_s
            FROM build_progress
            WHERE product_id = ?
            ORDER BY id ASC
        """, (product_id,)).fetchall()

    phases = [dict(row) for row in rows]

    # Calculate overall status
    statuses = [p["status"] for p in phases]
    if not phases:
        overall = "not_started"
    elif "failed" in statuses:
        overall = "failed"
    elif all(s in ("completed", "skipped") for s in statuses):
        overall = "completed"
    elif "running" in statuses or "starting" in statuses:
        overall = "in_progress"
    else:
        overall = "unknown"

    total_duration = sum(p.get("duration_s", 0) or 0 for p in phases)

    return json.dumps({
        "product_id": product_id,
        "overall_status": overall,
        "total_duration_s": round(total_duration, 1),
        "phases": phases,
    }, indent=2)


def get_active_builds() -> str:
    """
    Get all currently active (in-progress) builds.

    Returns:
        JSON string with list of active product builds and their current phase
    """
    _init_progress_table()
    with _conn() as conn:
        rows = conn.execute("""
            SELECT DISTINCT bp.product_id,
                   pps.product_name,
                   bp.phase as current_phase,
                   bp.status as phase_status,
                   bp.message,
                   bp.started_at
            FROM build_progress bp
            LEFT JOIN product_pipeline_state pps ON bp.product_id = pps.product_id
            WHERE bp.status IN ('starting', 'running')
            AND bp.id = (
                SELECT MAX(id) FROM build_progress
                WHERE product_id = bp.product_id
            )
            ORDER BY bp.started_at DESC
        """).fetchall()

    builds = [dict(row) for row in rows]
    return json.dumps({"active_builds": builds}, indent=2)
