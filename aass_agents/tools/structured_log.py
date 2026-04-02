"""
Structured Logging — JSON-formatted logs with run_id correlation.

Replaces print() statements with structured, filterable log output.
Every log line includes run_id for cross-cutting trace queries.

Uses Python's built-in logging with a JSON formatter (no external deps).
For production, swap the handler for Loguru/structlog/cloud logging.

Usage:
    from tools.structured_log import get_logger, bind_run_context

    log = get_logger("supervisor")
    bind_run_context(run_id="abc-123", agent_name="pm_agent")

    log.info("Agent started", extra={"phase": "prd"})
    # → {"ts":"2026-04-01T12:00:00Z","level":"INFO","logger":"supervisor",
    #    "run_id":"abc-123","agent":"pm_agent","msg":"Agent started","phase":"prd"}
"""
import contextvars
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Optional


# ── Context vars for correlation ─────────────────────────────────────────────

_log_run_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "log_run_id", default=""
)
_log_agent: contextvars.ContextVar[str] = contextvars.ContextVar(
    "log_agent", default=""
)
_log_department: contextvars.ContextVar[str] = contextvars.ContextVar(
    "log_department", default=""
)


def bind_run_context(
    run_id: str = "",
    agent_name: str = "",
    department: str = "",
) -> None:
    """Bind correlation fields to the current execution context."""
    if run_id:
        _log_run_id.set(run_id)
    if agent_name:
        _log_agent.set(agent_name)
    if department:
        _log_department.set(department)


def clear_run_context() -> None:
    """Clear all correlation fields."""
    _log_run_id.set("")
    _log_agent.set("")
    _log_department.set("")


# ── JSON Formatter ───────────────────────────────────────────────────────────

class JSONFormatter(logging.Formatter):
    """Formats log records as single-line JSON with correlation fields."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }

        # Inject correlation context
        run_id = _log_run_id.get()
        agent = _log_agent.get()
        department = _log_department.get()

        if run_id:
            entry["run_id"] = run_id
        if agent:
            entry["agent"] = agent
        if department:
            entry["department"] = department

        # Merge extra fields (from log.info("msg", extra={...}))
        for key in ("phase", "duration_ms", "error", "tool", "cost_usd",
                     "tokens", "status", "category", "event_type",
                     "pipeline", "wave", "strategy"):
            val = getattr(record, key, None)
            if val is not None:
                entry[key] = val

        # Include exception info if present
        if record.exc_info and record.exc_info[1]:
            entry["exception"] = str(record.exc_info[1])
            entry["exc_type"] = type(record.exc_info[1]).__name__

        return json.dumps(entry, default=str)


# ── Logger Factory ───────────────────────────────────────────────────────────

_configured = False


def _configure_root() -> None:
    """Configure the root aass logger once."""
    global _configured
    if _configured:
        return
    _configured = True

    root = logging.getLogger("aass")
    root.setLevel(logging.DEBUG)

    # JSON handler to stderr
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JSONFormatter())
    handler.setLevel(logging.INFO)
    root.addHandler(handler)

    # Prevent propagation to root logger (avoids duplicate output)
    root.propagate = False


def get_logger(name: str) -> logging.Logger:
    """
    Get a structured logger with JSON output and correlation support.

    Args:
        name: Logger name (e.g., "supervisor", "cost_tracker", "parallel_executor")

    Returns:
        Logger instance under the "aass" namespace
    """
    _configure_root()
    return logging.getLogger(f"aass.{name}")


# ── Convenience functions ────────────────────────────────────────────────────

def log_agent_start(run_id: str, agent_name: str, department: str = "") -> None:
    """Log agent start with context binding."""
    bind_run_context(run_id, agent_name, department)
    log = get_logger("agent")
    log.info("Agent started", extra={"status": "started"})


def log_agent_end(
    agent_name: str,
    duration_ms: int = 0,
    success: bool = True,
    error: str = "",
) -> None:
    """Log agent completion."""
    log = get_logger("agent")
    if success:
        log.info("Agent completed", extra={
            "status": "completed", "duration_ms": duration_ms,
        })
    else:
        log.warning("Agent failed", extra={
            "status": "failed", "duration_ms": duration_ms, "error": error,
        })


def log_tool_call(tool_name: str, agent_name: str = "") -> None:
    """Log a tool invocation."""
    log = get_logger("tool")
    log.info("Tool called", extra={"tool": tool_name})


def log_cost(
    agent_name: str,
    model_id: str,
    tokens: int,
    cost_usd: float,
) -> None:
    """Log a cost event."""
    log = get_logger("cost")
    log.info("Cost recorded", extra={
        "tokens": tokens, "cost_usd": cost_usd,
    })


def log_circuit_event(agent_name: str, state: str, category: str = "") -> None:
    """Log a circuit breaker state change."""
    log = get_logger("circuit")
    log.warning("Circuit breaker event", extra={
        "status": state, "category": category,
    })


def log_pipeline_event(
    pipeline: str,
    event_type: str,
    wave: int = -1,
    strategy: str = "",
) -> None:
    """Log a pipeline lifecycle event."""
    log = get_logger("pipeline")
    log.info("Pipeline event", extra={
        "pipeline": pipeline, "event_type": event_type,
        "wave": wave, "strategy": strategy,
    })
