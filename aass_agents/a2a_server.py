# aass_agents/a2a_server.py
"""
A2A Server — exposes AASS agents over the Agent2Agent protocol.

This allows external systems (DeerFlow, other ADK agents, any A2A client)
to communicate with AASS agents using the standardized A2A protocol.

Run:
    uvicorn a2a_server:app --port 8090

Environment variables:
    A2A_AGENT   — which agent to expose (default: "product_orchestrator")
    A2A_PORT    — port to bind (default: 8090)
    A2A_HOST    — host to bind (default: "0.0.0.0")
"""
import os
import logging

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO)
_log = logging.getLogger(__name__)

_agent_name = os.getenv("A2A_AGENT", "product_orchestrator")

# ── Import the requested agent ───────────────────────────────────────────────
_AGENT_MAP = {
    "product_orchestrator": "agents.product.product_orchestrator_agent:product_orchestrator",
    "company_orchestrator": "main:root_agent",
}


def _load_agent(name: str):
    """Dynamically import an agent by name."""
    if name not in _AGENT_MAP:
        raise ValueError(
            f"Unknown agent '{name}'. Available: {list(_AGENT_MAP.keys())}"
        )
    module_path, attr = _AGENT_MAP[name].rsplit(":", 1)
    import importlib
    mod = importlib.import_module(module_path)
    return getattr(mod, attr)


_agent = _load_agent(_agent_name)
_log.info("A2A Server: Loaded agent '%s'", _agent.name)

# ── Create the A2A app ──────────────────────────────────────────────────────
from agents._shared.a2a_bridge import expose_agent_a2a

_host = os.getenv("A2A_HOST", "0.0.0.0")
_port = int(os.getenv("A2A_PORT", "8090"))

app = expose_agent_a2a(_agent, host=_host, port=_port)
