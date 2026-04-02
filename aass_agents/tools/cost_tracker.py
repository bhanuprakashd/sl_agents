"""
Cost Tracker — intercepts litellm completions to record token usage.

Uses contextvars to pass run_id and agent_name through the call stack
without modifying ADK internals or agent signatures.
"""
import contextvars
import time
from typing import Optional

from tools.cost_tracker_db import record_cost_event, init_cost_tables

# ── Context vars (set by supervisor callbacks, read by interceptor) ──────────

_run_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "cost_run_id", default=None
)
_agent_name_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "cost_agent_name", default=None
)
_tier_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "cost_tier", default="std"
)


def set_cost_context(run_id: str, agent_name: str, tier: str = "std") -> None:
    """Set the cost tracking context for the current agent invocation."""
    _run_id_var.set(run_id)
    _agent_name_var.set(agent_name)
    _tier_var.set(tier)


def clear_cost_context() -> None:
    """Clear cost tracking context after agent completes."""
    _run_id_var.set(None)
    _agent_name_var.set(None)
    _tier_var.set("std")


def get_cost_context() -> tuple[Optional[str], Optional[str], str]:
    """Return (run_id, agent_name, tier) from context."""
    return _run_id_var.get(), _agent_name_var.get(), _tier_var.get()


# ── Response tracking ────────────────────────────────────────────────────────

def track_response(response: object, model_id: str, duration_ms: int = 0) -> None:
    """
    Extract token usage from a litellm response and record cost.
    No-op if no cost context is set (e.g. CLI usage without supervisor).
    """
    run_id, agent_name, tier = get_cost_context()
    if not run_id or not agent_name:
        return

    usage = getattr(response, "usage", None)
    if usage is None:
        return

    input_tokens = getattr(usage, "prompt_tokens", 0) or 0
    output_tokens = getattr(usage, "completion_tokens", 0) or 0
    cache_read_tokens = getattr(usage, "cache_read_input_tokens", 0) or 0
    cache_write_tokens = getattr(usage, "cache_creation_input_tokens", 0) or 0

    # Some providers put cache tokens in different fields
    if cache_read_tokens == 0:
        cache_read_tokens = getattr(usage, "prompt_tokens_details", None)
        if cache_read_tokens and hasattr(cache_read_tokens, "cached_tokens"):
            cache_read_tokens = cache_read_tokens.cached_tokens or 0
        else:
            cache_read_tokens = 0

    record_cost_event(
        run_id=run_id,
        agent_name=agent_name,
        model_id=model_id,
        tier=tier,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read_tokens,
        cache_write_tokens=cache_write_tokens,
        duration_ms=duration_ms,
    )


# ── Init ─────────────────────────────────────────────────────────────────────
init_cost_tables()
