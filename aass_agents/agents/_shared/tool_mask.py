"""
Tool Masking — Manus context engineering pattern.

Problem: When you remove a tool from an agent at runtime (e.g. to restrict what
a sub-agent can do in a given phase), you change the tool list in the prompt.
This invalidates the KV-cache prefix and forces a full re-computation.

Solution: Keep ALL tools in the prompt (stable prefix = cache hit). Instead of
removing tools, intercept their execution via ADK's before_tool_callback and
return a structured "unavailable" response. The model sees the tool in the list
but gets a clear signal it cannot use it right now.

Usage:
    from agents._shared.tool_mask import make_tool_mask

    # Only allow memory tools during the recall phase
    agent = Agent(
        ...,
        before_tool_callback=make_tool_mask(allowed=["recall_deal_context", "list_active_deals"]),
    )

    # Block specific tools explicitly
    agent = Agent(
        ...,
        before_tool_callback=make_tool_mask(blocked=["browser_crawl", "build_and_run"]),
    )
"""

from typing import Optional
from google.adk.agents.callback_context import CallbackContext
from google.adk.tools import BaseTool


def make_tool_mask(
    allowed: Optional[list[str]] = None,
    blocked: Optional[list[str]] = None,
) -> callable:
    """
    Return an ADK before_tool_callback that masks tools without removing them
    from the prompt, preserving the KV-cache prefix.

    Provide either:
      allowed: list of tool names that ARE permitted (all others are masked)
      blocked: list of tool names that are NOT permitted (all others pass through)

    If both are provided, a tool must be in `allowed` AND not in `blocked`.

    Args:
        allowed: Whitelist of tool names. If set, only these tools execute.
        blocked: Blacklist of tool names. If set, these tools are masked.

    Returns:
        A before_tool_callback function compatible with google.adk.agents.Agent.
    """
    allowed_set = set(allowed) if allowed else None
    blocked_set = set(blocked) if blocked else set()

    def _callback(
        tool: BaseTool,
        args: dict,
        tool_context: CallbackContext,
    ) -> Optional[dict]:
        """
        Return a masking response dict to block execution, or None to allow it.
        ADK interprets a non-None return as the tool result, skipping execution.
        """
        name = tool.name

        is_allowed = (allowed_set is None) or (name in allowed_set)
        is_blocked = name in blocked_set

        if is_allowed and not is_blocked:
            return None  # allow execution

        return {
            "error": (
                f"Tool '{name}' is not available in the current execution context. "
                f"Choose a different approach or use an available tool instead."
            ),
            "masked": True,
            "tool_name": name,
        }

    return _callback


# ── Preset masks for common scenarios ─────────────────────────────────────────

def memory_only_mask() -> callable:
    """Restrict agent to memory/recall tools only. Use during context-loading phase."""
    return make_tool_mask(allowed=[
        "recall_deal_context", "save_deal_context",
        "list_active_deals", "recall_past_outputs", "save_agent_output",
        "recall_product_state", "save_product_state", "log_step",
        "read_todo", "write_todo", "complete_todo_step", "get_todo_summary",
    ])


def no_write_mask() -> callable:
    """Block all write/mutating tools. Use for read-only analysis phases."""
    return make_tool_mask(blocked=[
        "save_deal_context", "save_agent_output",
        "save_product_state", "log_step",
        "write_todo", "complete_todo_step",
        "build_and_run", "build_review_improve", "build_with_feedback_loop",
        "browser_click", "browser_fill_form", "browser_solve_captcha",
    ])


def research_only_mask() -> callable:
    """Allow only research/read tools. Block builds and writes."""
    return make_tool_mask(allowed=[
        "deep_research", "search_company_web", "enrich_company",
        "find_contacts", "search_news",
        "navigate_and_read", "browser_screenshot", "browser_extract_links",
        "browser_crawl", "browser_run_script",
        "read_todo", "get_todo_summary",
        "recall_deal_context", "recall_past_outputs",
    ])


# ── Capability-based masks (powered by tool registry) ────────────────────────

def make_tool_mask_from_capabilities(*capabilities: str) -> callable:
    """
    Create a tool mask from capability tags instead of explicit name lists.
    Uses the tool registry to resolve capability -> tool names.

    Preserves KV-cache because the tool list in the prompt stays stable
    (masking, not removal).

    Usage:
        agent = Agent(
            ...,
            before_tool_callback=make_tool_mask_from_capabilities("research", "memory"),
        )
    """
    try:
        from tools.tool_registry import registry
        allowed_names = registry.get_tool_names_for_capabilities(*capabilities)
        if allowed_names:
            return make_tool_mask(allowed=allowed_names)
    except ImportError:
        pass

    # Fallback: allow everything if registry not available
    return make_tool_mask()


def make_tool_mask_for_department(department: str) -> callable:
    """
    Create a tool mask that only allows tools available to a department.

    Usage:
        agent = Agent(
            ...,
            before_tool_callback=make_tool_mask_for_department("sales"),
        )
    """
    try:
        from tools.tool_registry import registry
        entries = registry.find_by_department(department)
        allowed_names = [e.name for e in entries]
        if allowed_names:
            return make_tool_mask(allowed=allowed_names)
    except ImportError:
        pass

    return make_tool_mask()
