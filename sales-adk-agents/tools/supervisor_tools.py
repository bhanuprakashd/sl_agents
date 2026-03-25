"""
Read-only ADK-compatible tools for supervisor observability.
These may be exposed to orchestrators. They do NOT modify supervisor state.
Control-plane operations (reset-circuit, resume) are CLI-only via main.py.
"""
import json
import tools.supervisor_db as _db


def list_dlq() -> dict:
    """
    List all pipeline runs currently blocked in the dead letter queue.
    Read-only — does not modify supervisor state.

    Returns:
        dict with count and entries list, each entry having:
        run_id, pipeline_type, blocked_on, last_error, completed_steps, created_at
    """
    entries = _db.list_dlq_entries()
    for e in entries:
        if e.get("completed_steps_json"):
            e["completed_steps"] = json.loads(e["completed_steps_json"])
        else:
            e["completed_steps"] = []
    return {"count": len(entries), "entries": entries}


def log_to_dlq(agent_name: str, reason: str) -> dict:
    """
    Log an autoresearcher error to the dead letter queue.

    Used by rewriter_agent and rollback_watchdog_agent to record non-retryable
    failures (rate limit hits, file not found, syntax errors).

    Args:
        agent_name: The agent that triggered the error.
        reason: Human-readable description of the failure.

    Returns:
        dict with logged=True and the recorded details.
    """
    import uuid
    run_id = f"dlq-{agent_name}-{uuid.uuid4().hex[:8]}"
    _db.push_dlq(
        run_id=run_id,
        pipeline_type="autoresearcher",
        blocked_on=agent_name,
        last_error=reason,
        completed_steps=[],
    )
    return {"logged": True, "run_id": run_id, "agent_name": agent_name, "reason": reason}


def get_run_status(run_id: str) -> dict:
    """
    Get the current status of a pipeline run.
    Read-only — does not modify supervisor state.

    Args:
        run_id: The pipeline run UUID to look up.

    Returns:
        dict with found, run_id, pipeline_type, status, current_step, updated_at
        or found=False if not found.
    """
    row = _db.get_run(run_id)
    if not row:
        return {"found": False, "run_id": run_id}
    return {
        "found": True,
        "run_id": row["run_id"],
        "pipeline_type": row["pipeline_type"],
        "status": row["status"],
        "current_step": row["current_step"],
        "updated_at": row["updated_at"],
    }
