"""Memory tools — give agents access to the long-term SQLite memory store."""

from google.adk.tools import tool
from typing import Optional
import asyncio
import json


def _run(coro):
    """Run an async coroutine from a sync context (tool functions are sync)."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


@tool
def save_deal_context(company_name: str, deal_context_json: str, user_id: str = "default") -> dict:
    """
    Persist the current deal context for a company to long-term memory.
    Call this after every significant deal update so context survives session restarts.

    Args:
        company_name: Company name (used as the lookup key)
        deal_context_json: JSON string of the deal context fields to save
        user_id: Sales rep identifier (default: 'default')

    Returns:
        dict confirming the save
    """
    from shared.memory_store import save_deal_memory

    try:
        context = json.loads(deal_context_json)
    except json.JSONDecodeError as e:
        return {"error": f"Invalid JSON: {e}"}

    _run(save_deal_memory(company_name, context, user_id))
    return {"saved": True, "company": company_name, "fields": list(context.keys())}


@tool
def recall_deal_context(company_name: str, user_id: str = "default") -> dict:
    """
    Retrieve previously saved deal context for a company from long-term memory.
    Call this at the start of any session to restore prior deal state.

    Args:
        company_name: Company name to look up
        user_id: Sales rep identifier (default: 'default')

    Returns:
        dict with deal_context and updated_at, or empty if not found
    """
    from shared.memory_store import load_deal_memory

    result = _run(load_deal_memory(company_name, user_id))
    if result:
        return result
    return {"found": False, "company": company_name}


@tool
def list_active_deals(user_id: str = "default") -> dict:
    """
    List all companies with saved deal memory for the current rep.
    Use at session start to see all active deals.

    Args:
        user_id: Sales rep identifier (default: 'default')

    Returns:
        dict with list of companies and their last-updated timestamps
    """
    from shared.memory_store import list_deals

    deals = _run(list_deals(user_id))
    return {"deals": deals, "count": len(deals)}


@tool
def save_agent_output(
    company_name: str,
    agent_name: str,
    query: str,
    output: str,
    user_id: str = "default",
) -> dict:
    """
    Save an agent's output to query history for future recall.
    Call after any significant agent output (research profiles, proposals, call briefs).

    Args:
        company_name: Company the output is about
        agent_name: Which agent produced the output (e.g., 'lead_researcher')
        query: The original request that triggered the output
        output: The full output text to save
        user_id: Sales rep identifier

    Returns:
        dict confirming the save
    """
    from shared.memory_store import save_query

    _run(save_query(company_name, agent_name, query, output, user_id))
    return {"saved": True, "company": company_name, "agent": agent_name}


@tool
def recall_past_outputs(
    company_name: str,
    agent_name: Optional[str] = None,
    limit: int = 3,
    user_id: str = "default",
) -> dict:
    """
    Recall past agent outputs for a company from query history.
    Use to avoid re-doing work already done in a previous session.

    Args:
        company_name: Company to recall history for
        agent_name: Filter by agent name (optional — omit to get all agents)
        limit: Max number of past outputs to return (default 3)
        user_id: Sales rep identifier

    Returns:
        dict with list of past outputs sorted by most recent first
    """
    from shared.memory_store import recall_queries

    history = _run(recall_queries(company_name, agent_name, limit, user_id))
    return {
        "company": company_name,
        "history": history,
        "count": len(history),
    }
