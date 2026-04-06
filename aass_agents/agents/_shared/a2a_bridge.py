# aass_agents/agents/_shared/a2a_bridge.py
"""
A2A Bridge — connects AASS agents with DeerFlow and other external agent systems.

Provides:
  1. deerflow_research_agent — RemoteA2aAgent that delegates deep research to DeerFlow
  2. expose_agent_a2a() — helper to expose any AASS agent as an A2A server

Usage in agent definitions:
    from agents._shared.a2a_bridge import deerflow_research_agent

    # Add as a sub-agent to any orchestrator:
    my_orchestrator = Agent(
        sub_agents=[..., deerflow_research_agent],
    )

Environment variables:
    DEERFLOW_A2A_URL — DeerFlow A2A endpoint (default: http://localhost:8001)
    A2A_ENABLED      — set to "0" to disable A2A agents (default: "1")
"""
import os
import logging

_log = logging.getLogger(__name__)

A2A_ENABLED = os.getenv("A2A_ENABLED", "1") != "0"

# ── DeerFlow as a remote A2A agent ───────────────────────────────────────────

_DEERFLOW_URL = os.getenv("DEERFLOW_A2A_URL", "http://localhost:8001")

deerflow_research_agent = None

if A2A_ENABLED:
    try:
        from google.adk.agents.remote_a2a_agent import (
            RemoteA2aAgent,
            AGENT_CARD_WELL_KNOWN_PATH,
        )

        deerflow_research_agent = RemoteA2aAgent(
            name="deerflow_research_agent",
            description=(
                "Delegates deep research tasks to DeerFlow (LangGraph-based super agent). "
                "Use for: multi-source web research, competitive analysis, market research, "
                "technology deep dives, and any task requiring sandbox code execution. "
                "DeerFlow has 12 middlewares, web search/fetch, and sandbox execution."
            ),
            agent_card=f"{_DEERFLOW_URL}{AGENT_CARD_WELL_KNOWN_PATH}",
            use_legacy=False,
        )
        _log.info("A2A: DeerFlow research agent configured at %s", _DEERFLOW_URL)

    except ImportError:
        _log.warning("A2A: a2a-sdk not installed, DeerFlow bridge unavailable. "
                     "Install with: pip install 'google-adk[a2a]'")
    except Exception as exc:
        _log.warning("A2A: Failed to create DeerFlow bridge: %s", exc)
else:
    _log.info("A2A: Disabled via A2A_ENABLED=0")


def get_a2a_agents() -> list:
    """Return list of available A2A remote agents (non-None only)."""
    agents = []
    if deerflow_research_agent is not None:
        agents.append(deerflow_research_agent)
    return agents


# ── Expose AASS agents as A2A servers ────────────────────────────────────────

def expose_agent_a2a(agent, host: str = "0.0.0.0", port: int = 8080):
    """
    Expose an ADK agent as an A2A server.

    Args:
        agent: Any ADK Agent instance
        host: Bind address
        port: Bind port

    Returns:
        FastAPI app configured with A2A endpoints

    Usage:
        from agents._shared.a2a_bridge import expose_agent_a2a
        from agents.product.product_orchestrator_agent import product_orchestrator

        app = expose_agent_a2a(product_orchestrator, port=8090)
        # Run with: uvicorn a2a_server:app --port 8090
    """
    try:
        from google.adk.a2a.utils.agent_to_a2a import convert_agent_to_a2a
    except ImportError:
        raise ImportError(
            "A2A server support requires: pip install 'google-adk[a2a]'"
        )

    a2a_app = convert_agent_to_a2a(
        agent=agent,
        host=host,
        port=port,
    )
    _log.info("A2A: Exposing agent '%s' on %s:%d", agent.name, host, port)
    return a2a_app
