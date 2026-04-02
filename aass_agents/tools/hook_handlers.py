"""
Hook Handlers — concrete handler functions for the declarative hook system.

Each function receives a context dict with:
  - run_id: str | None
  - agent_name: str
  - input_text: str (pre_agent) or output_text: str (post_agent)
  - state: dict (session state)
  - supervisor: Supervisor instance

Returns None to allow, or a Content object to block (pre_agent only).
"""
from typing import Any, Optional

from tools.structured_log import (
    get_logger, bind_run_context, clear_run_context,
    log_agent_start, log_agent_end, log_circuit_event,
)

_log = get_logger("hooks")


def _get_supervisor():
    """Lazy import to avoid circular dependency."""
    from tools.supervisor import Supervisor
    return Supervisor()


# Cache a single supervisor instance
_supervisor: Optional[Any] = None


def _sup() -> Any:
    global _supervisor
    if _supervisor is None:
        _supervisor = _get_supervisor()
    return _supervisor


# ── Pre-Agent Hooks ──────────────────────────────────────────────────────────

def check_circuit_breaker(context: dict) -> Optional[Any]:
    """Check if the agent's circuit breaker is open."""
    run_id = context.get("run_id")
    agent_name = context.get("agent_name", "")

    if not run_id:
        return None

    # Skip orchestrators and meta-agents
    skip = (
        "reflection_agent", "company_orchestrator",
        "sales_orchestrator", "marketing_orchestrator",
        "product_orchestrator", "engineering_orchestrator",
        "research_orchestrator", "qa_orchestrator",
    )
    if agent_name in skip:
        return None

    msg = _sup().circuit_breaker.check(agent_name)
    if msg:
        _sup()._db.append_event(run_id, agent_name, "circuit.opened", {"message": msg})
        log_circuit_event(agent_name, "blocked", "open")
        return _make_content(msg)
    return None


def check_loop_guard(context: dict) -> Optional[Any]:
    """Check for repeated agent calls."""
    run_id = context.get("run_id")
    agent_name = context.get("agent_name", "")
    input_text = context.get("input_text", "")

    if not run_id:
        return None

    skip = (
        "reflection_agent", "company_orchestrator",
        "sales_orchestrator", "marketing_orchestrator",
        "product_orchestrator", "engineering_orchestrator",
        "research_orchestrator", "qa_orchestrator",
    )
    if agent_name in skip:
        return None

    msg = _sup().loop_guard.check(run_id, agent_name, input_text)
    if msg:
        _sup()._db.append_event(run_id, agent_name, "loop.detected", {"message": msg})
        return _make_content(msg)
    return None


def set_cost_context(context: dict) -> None:
    """Set cost tracking context vars."""
    run_id = context.get("run_id")
    agent_name = context.get("agent_name", "")
    if run_id and agent_name:
        from tools.cost_tracker import set_cost_context as _set
        _set(run_id, agent_name)


def set_message_context(context: dict) -> None:
    """Set inter-agent messaging context."""
    run_id = context.get("run_id")
    agent_name = context.get("agent_name", "")
    if run_id and agent_name:
        from tools.message_bus import set_message_context as _set
        _set(run_id, agent_name)


def log_agent_called(context: dict) -> None:
    """Log agent invocation to supervisor + structured log."""
    run_id = context.get("run_id")
    agent_name = context.get("agent_name", "")
    input_text = context.get("input_text", "")
    if run_id:
        _sup().log_called(run_id, agent_name, input_text)
        log_agent_start(run_id, agent_name)


# ── Post-Agent Hooks ─────────────────────────────────────────────────────────

def log_agent_returned(context: dict) -> None:
    """Log agent completion to supervisor + structured log."""
    run_id = context.get("run_id")
    agent_name = context.get("agent_name", "")
    output_text = context.get("output_text", "")
    error = context.get("error")
    if run_id:
        _sup().log_returned(run_id, agent_name, output_text, error=error)
        log_agent_end(agent_name, success=error is None, error=error or "")


def checkpoint_run(context: dict) -> None:
    """Checkpoint the pipeline run."""
    run_id = context.get("run_id")
    agent_name = context.get("agent_name", "")
    if run_id:
        _sup().checkpoint(run_id, agent_name)


def update_validity(context: dict) -> None:
    """Update staleness/validity cache."""
    run_id = context.get("run_id")
    agent_name = context.get("agent_name", "")
    state = context.get("state", {})
    if run_id:
        _sup().update_validity(run_id, agent_name, state)


def clear_cost_context(context: dict) -> None:
    """Clear cost tracking context."""
    from tools.cost_tracker import clear_cost_context as _clear
    _clear()


def clear_message_context(context: dict) -> None:
    """Clear messaging context + structured log context."""
    from tools.message_bus import clear_message_context as _clear
    _clear()
    clear_run_context()


def emit_progress(context: dict) -> None:
    """Broadcast agent completion to SSE subscribers."""
    run_id = context.get("run_id")
    agent_name = context.get("agent_name", "")
    if run_id:
        from tools.progress_callbacks import broadcaster
        broadcaster.emit_sync(
            product_id=run_id,
            phase=agent_name,
            status="completed",
            agent_name=agent_name,
            event_type="agent.completed",
        )


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_content(text: str):
    """Create an ADK Content object for blocking responses."""
    from google.genai.types import Content, Part
    return Content(parts=[Part(text=text)])
