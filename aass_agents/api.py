"""
SL Agents — FastAPI backend for the dashboard UI.

Serves the dashboard and streams ADK agent events via SSE.

Run:
    uvicorn api:app --reload --port 8080 --timeout-keep-alive 5400

Then open: http://localhost:8080
"""

import asyncio
import json
import os
import time
import uuid
from pathlib import Path
from typing import AsyncGenerator, Optional as Opt

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel

from google.adk.runners import Runner
from google.genai.types import Content, Part

from main import root_agent
from agents._shared.session_store import (
    get_session_service,
    list_sessions,
    get_session_state,
    get_checkpoint_stages,
)
from tools.pipeline_metrics import (
    start_run, end_run,
    record_stage_start, record_stage_end,
    get_run_metrics, get_pipeline_stats, get_recent_runs,
)
from tools.supervisor_db import (
    init_supervisor_tables,
    _get_conn as sup_conn,
    get_circuit,
    upsert_circuit,
    list_dlq_entries,
    get_run,
    AGENT_TTL_DAYS,
)
from tools.skill_forge_db import SKILL_FORGE_DB_PATH
from tools.evolution_db import EVOLUTION_DB_PATH

init_supervisor_tables()

app = FastAPI(title="SL Agents API", docs_url="/api/docs")

_start_time = time.time()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

APP_NAME = "sl-agents-ui"
_session_service = get_session_service()

GENERATED_SKILLS_PATH = Path(__file__).parent.parent / "generated_skills" / "_registry.json"


# ── Models ────────────────────────────────────────────────────────────────────

class RunRequest(BaseModel):
    prompt: str
    session_id: str | None = None


# ── SSE helpers ───────────────────────────────────────────────────────────────

def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


def _extract_parts(event) -> tuple[str, list[dict], list[dict]]:
    """Return (text, tool_calls, tool_results) from an ADK event."""
    text = ""
    tool_calls = []
    tool_results = []
    if not (event.content and event.content.parts):
        return text, tool_calls, tool_results
    for part in event.content.parts:
        if hasattr(part, "text") and part.text:
            text += part.text
        if hasattr(part, "function_call") and part.function_call:
            fc = part.function_call
            tool_calls.append({
                "name": fc.name,
                "args": dict(fc.args) if fc.args else {},
            })
        if hasattr(part, "function_response") and part.function_response:
            fr = part.function_response
            resp = fr.response
            if isinstance(resp, dict):
                resp_str = json.dumps(resp)[:600]
            else:
                resp_str = str(resp)[:600]
            tool_results.append({"name": fr.name, "result": resp_str})
    return text, tool_calls, tool_results


async def _stream_run(prompt: str, session_id: str) -> AsyncGenerator[str, None]:
    # Create session (ignore if already exists)
    try:
        await _session_service.create_session(
            app_name=APP_NAME, user_id="ui-user", session_id=session_id,
        )
    except Exception:
        pass

    runner = Runner(
        agent=root_agent,
        app_name=APP_NAME,
        session_service=_session_service,
    )

    run_id = str(uuid.uuid4())
    metrics_run_id = start_run("product_pipeline", prompt)
    _current_stage: dict = {"name": None}  # track current stage for metrics
    yield _sse({"type": "run_start", "run_id": run_id, "metrics_run_id": metrics_run_id, "prompt": prompt})

    consumer_task = None
    try:
        # Wrap the async iterator with a keepalive mechanism.
        # Long-running tool calls (build_with_feedback_loop can take 40-90 min)
        # produce no events, causing the SSE connection to drop due to inactivity.
        # We send a keepalive comment every 10 seconds to prevent this.
        event_queue: asyncio.Queue = asyncio.Queue()
        _SENTINEL = object()
        _consumer_error: list = []  # capture consumer-side errors

        async def _consume_events():
            try:
                async for event in runner.run_async(
                    user_id="ui-user",
                    session_id=session_id,
                    new_message=Content(role="user", parts=[Part(text=prompt)]),
                ):
                    await event_queue.put(event)
            except asyncio.CancelledError:
                pass  # generator closed by client disconnect — clean exit
            except Exception as exc:
                _consumer_error.append(exc)
                await event_queue.put(exc)
            finally:
                await event_queue.put(_SENTINEL)

        consumer_task = asyncio.create_task(_consume_events())

        while True:
            try:
                item = await asyncio.wait_for(event_queue.get(), timeout=10.0)
            except asyncio.TimeoutError:
                # Check if consumer died silently (task done but no sentinel)
                if consumer_task.done():
                    # Consumer finished without sending sentinel — check for error
                    if _consumer_error:
                        raise _consumer_error[0]
                    break
                # No event for 10s — send keepalive to prevent connection drop
                yield ": keepalive\n\n"
                continue

            if item is _SENTINEL:
                break

            if isinstance(item, Exception):
                raise item

            event = item
            author = getattr(event, "author", None) or "unknown"
            text, tool_calls, tool_results = _extract_parts(event)

            # Track stage transitions for metrics
            if author != _current_stage["name"] and author != "unknown":
                if _current_stage["name"]:
                    record_stage_end(metrics_run_id, _current_stage["name"], status="success")
                _current_stage["name"] = author
                record_stage_start(metrics_run_id, author)

            for tc in tool_calls:
                yield _sse({"type": "tool_call", "agent": author,
                            "tool": tc["name"], "args": tc["args"]})

            for tr in tool_results:
                yield _sse({"type": "tool_result", "agent": author,
                            "tool": tr["name"], "result": tr["result"]})

            if text:
                if event.is_final_response():
                    yield _sse({"type": "final", "agent": author, "text": text})
                else:
                    yield _sse({"type": "agent_text", "agent": author, "text": text})

        # Close the last stage and end the run
        if _current_stage["name"]:
            record_stage_end(metrics_run_id, _current_stage["name"], status="success")
        end_run(metrics_run_id, status="success")
        yield _sse({"type": "done", "metrics_run_id": metrics_run_id})

    except Exception as exc:
        import traceback
        tb = traceback.format_exc()
        print(f"[STREAM ERROR] {exc}\n{tb}", flush=True)
        # Record failure in metrics
        if _current_stage["name"]:
            record_stage_end(metrics_run_id, _current_stage["name"],
                             status="failed", error_message=str(exc))
        end_run(metrics_run_id, status="failed")
        yield _sse({"type": "error", "message": str(exc), "traceback": tb})
        yield _sse({"type": "done", "metrics_run_id": metrics_run_id})
    finally:
        # Ensure consumer task is cleaned up even if client disconnects
        if consumer_task and not consumer_task.done():
            consumer_task.cancel()
            try:
                await consumer_task
            except (asyncio.CancelledError, Exception):
                pass


# ── Routes ────────────────────────────────────────────────────────────────────

@app.post("/api/run")
async def run_agent(req: RunRequest):
    """Stream agent execution events via SSE."""
    session_id = req.session_id or str(uuid.uuid4())
    return StreamingResponse(
        _stream_run(req.prompt, session_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/skills")
async def get_skills():
    """Return the staged skills registry."""
    if GENERATED_SKILLS_PATH.exists():
        return json.loads(GENERATED_SKILLS_PATH.read_text())
    return {"version": "1.0", "skills": []}


@app.get("/api/status")
async def get_status():
    """Return system status."""
    return {
        "status": "running",
        "model": os.getenv("MODEL_ID", "gemini-2.0-flash"),
        "agent": root_agent.name,
    }


# ── Task 1: Expanded status & supervisor stats ────────────────────────────────

@app.get("/api/status/live")
async def status_live():
    """Expanded status for the top bar."""
    conn = sup_conn()
    try:
        active_runs = conn.execute(
            "SELECT COUNT(*) FROM supervisor_runs WHERE status IN ('pending', 'running')"
        ).fetchone()[0]
        open_breakers = conn.execute(
            "SELECT COUNT(*) FROM supervisor_circuit_breakers WHERE state = 'open'"
        ).fetchone()[0]
        dlq_count = conn.execute(
            "SELECT COUNT(*) FROM supervisor_dlq"
        ).fetchone()[0]
    finally:
        conn.close()
    return {
        "status": "operational",
        "model": os.getenv("MODEL_ID", "gemini-2.0-flash"),
        "agent": "company_orchestrator",
        "agent_count": 62,
        "department_count": 9,
        "active_runs": active_runs,
        "open_breakers": open_breakers,
        "dlq_count": dlq_count,
        "uptime_seconds": int(time.time() - _start_time),
    }


@app.get("/api/supervisor/stats")
async def supervisor_stats():
    """KPI summary for the dashboard command center."""
    conn = sup_conn()
    try:
        active_runs = conn.execute(
            "SELECT COUNT(*) FROM supervisor_runs WHERE status IN ('pending', 'running')"
        ).fetchone()[0]
        open_breakers = conn.execute(
            "SELECT COUNT(*) FROM supervisor_circuit_breakers WHERE state = 'open'"
        ).fetchone()[0]
        dlq_count = conn.execute(
            "SELECT COUNT(*) FROM supervisor_dlq"
        ).fetchone()[0]
        events_24h = conn.execute(
            "SELECT COUNT(*) FROM supervisor_events WHERE created_at > datetime('now', '-1 day')"
        ).fetchone()[0]
    finally:
        conn.close()
    return {
        "active_runs": active_runs,
        "open_breakers": open_breakers,
        "dlq_count": dlq_count,
        "events_24h": events_24h,
    }


# ── Task 2: Circuits, DLQ, runs, events ──────────────────────────────────────

@app.get("/api/supervisor/circuits")
async def supervisor_circuits():
    """All circuit breaker states."""
    conn = sup_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM supervisor_circuit_breakers ORDER BY state DESC, agent_name"
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


@app.post("/api/supervisor/circuits/{agent_name}/reset")
async def reset_circuit(agent_name: str):
    """Reset a circuit breaker to closed state."""
    upsert_circuit(agent_name, failure_count=0, state="closed",
                   last_failure_at=None, opened_at=None)
    return {"success": True, "agent_name": agent_name}


@app.get("/api/supervisor/dlq")
async def supervisor_dlq():
    """All dead letter queue entries."""
    return list_dlq_entries()


@app.post("/api/supervisor/dlq/{run_id}/resume")
async def resume_dlq(run_id: str):
    """Remove a run from DLQ so it can be re-queued."""
    conn = sup_conn()
    try:
        conn.execute("DELETE FROM supervisor_dlq WHERE run_id = ?", (run_id,))
        conn.commit()
    finally:
        conn.close()
    return {"success": True, "run_id": run_id}


@app.get("/api/supervisor/runs")
async def supervisor_runs(status: Opt[str] = None, type: Opt[str] = None, limit: int = 20):
    """Pipeline runs — filterable by status, type."""
    conn = sup_conn()
    try:
        query = "SELECT * FROM supervisor_runs WHERE 1=1"
        params: list = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if type:
            query += " AND pipeline_type = ?"
            params.append(type)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


@app.get("/api/supervisor/events")
async def supervisor_events(
    agent: Opt[str] = None,
    type: Opt[str] = None,
    run_id: Opt[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    """Event log — filterable, paginated."""
    conn = sup_conn()
    try:
        query = "SELECT * FROM supervisor_events WHERE 1=1"
        params: list = []
        if agent:
            query += " AND agent_name = ?"
            params.append(agent)
        if type:
            query += " AND event_type = ?"
            params.append(type)
        if run_id:
            query += " AND run_id = ?"
            params.append(run_id)
        query += " ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


# ── Task 3: Evolution history, forge registry, agent status ──────────────────

@app.get("/api/supervisor/evolution")
async def supervisor_evolution():
    """Evolution history — agent versions joined with hypotheses."""
    import sqlite3
    conn = sqlite3.connect(str(EVOLUTION_DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("""
            SELECT v.agent_name, v.version, v.status, v.score_baseline,
                   v.baseline_sampled_at, v.created_at,
                   h.root_cause, h.hypothesis_text, h.confidence
            FROM agent_versions v
            LEFT JOIN hypotheses h ON h.agent_name = v.agent_name AND h.version = v.version
            ORDER BY v.created_at DESC
        """).fetchall()
    except Exception:
        return []
    finally:
        conn.close()
    return [dict(r) for r in rows]


@app.get("/api/forge/registry")
async def forge_registry():
    """Staged skills from the Skill Forge pipeline."""
    import sqlite3
    conn = sqlite3.connect(str(SKILL_FORGE_DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT * FROM staging_registry ORDER BY updated_at DESC"
        ).fetchall()
    except Exception:
        return {"skills": []}
    finally:
        conn.close()
    return {"skills": [dict(r) for r in rows]}


@app.get("/api/agents/status")
async def agents_status():
    """Live status for all agents — circuit state, last invoked, cache validity."""
    conn = sup_conn()
    try:
        circuits = conn.execute("SELECT * FROM supervisor_circuit_breakers").fetchall()
        circuit_map = {r["agent_name"]: dict(r) for r in circuits}
        last_invoked = conn.execute("""
            SELECT agent_name, MAX(created_at) as last_invoked
            FROM supervisor_events
            WHERE event_type = 'agent.called'
            GROUP BY agent_name
        """).fetchall()
        invoked_map = {r["agent_name"]: r["last_invoked"] for r in last_invoked}
    finally:
        conn.close()
    results = []
    for agent_name in AGENT_TTL_DAYS:
        if agent_name == "_default":
            continue
        c = circuit_map.get(agent_name, {})
        results.append({
            "name": agent_name,
            "circuit_state": c.get("state", "closed"),
            "failure_count": c.get("failure_count", 0),
            "last_invoked": invoked_map.get(agent_name),
            "ttl_days": (ttl if (ttl := AGENT_TTL_DAYS.get(agent_name)) is not None and ttl != float("inf") else None),
            "ttl_permanent": AGENT_TTL_DAYS.get(agent_name) == float("inf"),
        })
    return results


# ── Build Progress Endpoints ──────────────────────────────────────────
from tools.build_progress import get_build_progress, get_active_builds
from tools.skill_memory import find_similar_skills, get_skill_context

@app.get("/api/build/progress/{product_id}")
async def api_build_progress(product_id: str):
    """Get build phase progress for a specific product."""
    import json as _json
    return _json.loads(get_build_progress(product_id))

@app.get("/api/build/active")
async def api_active_builds():
    """Get all currently active (in-progress) builds."""
    import json as _json
    return _json.loads(get_active_builds())

@app.get("/api/build/progress/{product_id}/stream")
async def api_build_progress_stream(product_id: str):
    """SSE stream of build progress for real-time dashboard updates."""
    import json as _json

    async def _stream():
        last_data = ""
        for _ in range(600):  # 10 minutes max
            data = get_build_progress(product_id)
            if data != last_data:
                last_data = data
                yield f"data: {data}\n\n"
                parsed = _json.loads(data)
                if parsed.get("overall_status") in ("completed", "failed"):
                    break
            await asyncio.sleep(2)
        yield "data: {\"type\": \"done\"}\n\n"

    return StreamingResponse(_stream(), media_type="text/event-stream")

@app.get("/api/skills/similar")
async def api_similar_skills(product_name: str = "", product_type: str = ""):
    """Find similar past builds for skill reuse."""
    import json as _json
    prd = {"product_type": product_type} if product_type else {}
    return _json.loads(find_similar_skills(product_name, prd))


# ── Feedback Loop endpoints ──────────────────────────────────────

@app.get("/api/feedback/{product_id}")
async def api_feedback_history(product_id: str):
    """Get feedback round history for a product build."""
    import json as _json
    from tools.human_feedback_loop import get_feedback_history
    return _json.loads(get_feedback_history(product_id))


@app.get("/api/feedback/patterns/common")
async def api_feedback_patterns(limit: int = 20):
    """Get most common feedback patterns across all builds for learning."""
    import json as _json
    from tools.human_feedback_loop import get_feedback_patterns
    return _json.loads(get_feedback_patterns(limit=limit))


# ── Cost Tracking Endpoints ──────────────────────────────────────────────────
from tools.cost_tracker_db import get_cost_summary, get_costs_by_run, get_costs_by_agent, get_costs_by_department
from agents._shared.agent_registry import AGENT_DEPARTMENT_MAP, ALL_DEPARTMENTS

@app.get("/api/costs/summary")
async def api_cost_summary(since: Opt[str] = None):
    """Aggregate cost summary — total tokens, USD, breakdown by tier and agent."""
    return get_cost_summary(since)

@app.get("/api/costs/by-run/{run_id}")
async def api_costs_by_run(run_id: str):
    """All cost events for a specific pipeline run."""
    return get_costs_by_run(run_id)

@app.get("/api/costs/by-agent")
async def api_costs_by_agent(agent: str, since: Opt[str] = None):
    """Cost events for a specific agent."""
    return get_costs_by_agent(agent, since)

@app.get("/api/costs/by-department/{department}")
async def api_costs_by_department(department: str, since: Opt[str] = None):
    """Aggregate costs for all agents in a department."""
    return get_costs_by_department(department, AGENT_DEPARTMENT_MAP, since)

@app.get("/api/costs/departments")
async def api_cost_departments():
    """List all departments with their agent counts."""
    return {
        dept: len([a for a, d in AGENT_DEPARTMENT_MAP.items() if d == dept])
        for dept in ALL_DEPARTMENTS
    }


# ── Progress Streaming Endpoints ─────────────────────────────────────────────
from tools.progress_callbacks import broadcaster

@app.get("/api/events/stream")
async def api_global_event_stream():
    """SSE stream of ALL progress events system-wide (for dashboard monitor)."""
    async def _stream():
        async for event in broadcaster.subscribe():
            yield f"data: {json.dumps(event)}\n\n"
    return StreamingResponse(_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@app.get("/api/events/stream/{product_id}")
async def api_product_event_stream(product_id: str):
    """SSE stream of progress events for a specific product/run."""
    async def _stream():
        async for event in broadcaster.subscribe(product_id):
            yield f"data: {json.dumps(event)}\n\n"
            if event.get("status") in ("completed", "failed"):
                break
    return StreamingResponse(_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── Inter-Agent Messaging Endpoints ──────────────────────────────────────────
from tools.message_bus_db import get_all_messages as get_run_messages, read_messages as get_agent_messages

@app.get("/api/messages/{run_id}")
async def api_messages_by_run(run_id: str):
    """All inter-agent messages for a pipeline run."""
    return get_run_messages(run_id)

@app.get("/api/messages/{run_id}/{agent_name}")
async def api_messages_by_agent(run_id: str, agent_name: str):
    """Pending messages for a specific agent in a run."""
    return get_agent_messages(run_id, agent_name, mark_read=False)


# ── Tool Registry Endpoints ─────────────────────────────────────────────────
from tools.tool_registry import registry as _tool_registry
from pathlib import Path as _Path
_tool_registry.load_from_yaml(str(_Path(__file__).parent / "tool_registry.yaml"))

@app.get("/api/tools/registry")
async def api_tool_registry(capability: Opt[str] = None, department: Opt[str] = None):
    """Query the tool registry by capability and/or department."""
    if capability and department:
        entries = [
            e for e in _tool_registry.find_by_any_capability(capability)
            if department in e.departments or "all" in e.departments
        ]
    elif capability:
        entries = _tool_registry.find_by_any_capability(capability)
    elif department:
        entries = _tool_registry.find_by_department(department)
    else:
        entries = _tool_registry.list_all()

    return {
        "tools": [
            {"name": e.name, "capabilities": list(e.capabilities),
             "departments": list(e.departments), "tier": e.tier,
             "description": e.description}
            for e in entries
        ],
        "count": len(entries),
    }

@app.get("/api/tools/capabilities")
async def api_tool_capabilities():
    """List all unique tool capabilities."""
    return _tool_registry.list_capabilities()


# ── Hook System Endpoints ────────────────────────────────────────────────────
from main import _hooks

@app.get("/api/hooks")
async def api_list_hooks():
    """List all registered lifecycle hooks."""
    return _hooks.list_hooks()

@app.post("/api/hooks/reload")
async def api_reload_hooks():
    """Hot-reload hooks from hooks.yaml."""
    import os
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hooks.yaml")
    _hooks.reload(config_path)
    return {"success": True, "hooks": len(_hooks.list_hooks())}


# ── Audit Log Endpoints ─────────────────────────────────────────────────────
from tools.supervisor_db import get_audit_log, verify_audit_chain

@app.get("/api/supervisor/audit")
async def api_audit_log(run_id: Opt[str] = None, agent: Opt[str] = None, limit: int = 100):
    """Query the immutable audit trail."""
    return get_audit_log(run_id, agent, limit)

@app.get("/api/supervisor/audit/{run_id}/verify")
async def api_verify_audit(run_id: str):
    """Verify the integrity of the audit chain for a run."""
    return verify_audit_chain(run_id)


# ── Skill Forge Graduation Endpoints ─────────────────────────────────────────
from tools.skill_forge_db import (
    check_promotion_eligible, promote_skill_sync,
    demote_skill_sync, get_promotion_dashboard_sync,
)

@app.get("/api/forge/promotion-dashboard")
async def api_promotion_dashboard():
    """Skill promotion status — eligible, needs review, not ready."""
    return get_promotion_dashboard_sync()

@app.get("/api/forge/check/{skill_id}")
async def api_check_promotion(skill_id: str):
    """Check if a specific skill is eligible for promotion."""
    return check_promotion_eligible(skill_id)

@app.post("/api/forge/promote/{skill_id}")
async def api_promote_skill(skill_id: str):
    """Promote a staged skill to active status."""
    return promote_skill_sync(skill_id)

@app.post("/api/forge/demote/{skill_id}")
async def api_demote_skill(skill_id: str, reason: str = ""):
    """Demote a skill back to review-needed state."""
    return demote_skill_sync(skill_id, reason)


# ── Parallel Pipeline Endpoints ──────────────────────────────────────────────
from agents._shared.pipeline_defs import PIPELINES

@app.get("/api/pipelines")
async def api_list_pipelines():
    """List available parallel pipelines."""
    return {
        name: {
            "tasks": [
                {"agent": t.agent_name, "depends_on": list(t.depends_on)}
                for t in tasks
            ],
            "task_count": len(tasks),
        }
        for name, tasks in PIPELINES.items()
    }


# ── MCP Hub Endpoints ────────────────────────────────────────────────────────
from agents._shared.mcp_hub import mcp_hub

@app.get("/api/mcp/servers")
async def api_mcp_servers():
    """List all available MCP servers and their connection status."""
    return mcp_hub.list_available()

@app.get("/api/mcp/capabilities")
async def api_mcp_capabilities():
    """List all registered MCP capability names."""
    return mcp_hub.list_all_capabilities()


# ── Pipeline Metrics Endpoints ───────────────────────────────────────────────

@app.get("/api/metrics/run/{run_id}")
async def api_run_metrics(run_id: str):
    """Get full metrics for a pipeline run including all stage timings."""
    return get_run_metrics(run_id)


@app.get("/api/metrics/stats")
async def api_pipeline_stats(pipeline: Opt[str] = None, hours: int = 24):
    """Aggregate pipeline statistics: success rate, avg duration, stage breakdown."""
    return get_pipeline_stats(pipeline, hours)


@app.get("/api/metrics/runs")
async def api_recent_runs(limit: int = 20):
    """Get most recent pipeline runs with status and timing."""
    return get_recent_runs(limit)


# ── Session Persistence & Resume Endpoints ──────────────────────────────────

@app.get("/api/sessions")
async def api_list_sessions(user_id: str = "ui-user"):
    """List all persisted sessions for a user."""
    return await list_sessions(_session_service, APP_NAME, user_id)


@app.get("/api/sessions/{session_id}")
async def api_get_session(session_id: str, user_id: str = "ui-user"):
    """Get full state for a session — shows which pipeline stages completed."""
    data = await get_session_state(_session_service, APP_NAME, user_id, session_id)
    if "error" not in data:
        data["checkpoint"] = get_checkpoint_stages(data.get("state", {}))
    return data


@app.post("/api/sessions/{session_id}/resume")
async def api_resume_session(session_id: str, user_id: str = "ui-user"):
    """Resume a pipeline from its last checkpoint.

    Sends a 'continue' message to the existing session, which causes the
    runner to pick up from where the SequentialAgent left off (the next
    agent whose output_key is not yet in state).
    """
    return StreamingResponse(
        _stream_run("Continue the pipeline from where it left off.", session_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/favicon.ico")
async def favicon():
    # Return 204 No Content if no favicon file exists
    return Response(status_code=204)


@app.get("/")
async def serve_dashboard():
    return FileResponse("dashboard.html")
