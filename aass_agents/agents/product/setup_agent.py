# aass_agents/agents/product/setup_agent.py
"""
Setup Agent — initializes the product pipeline run.

Generates a product_id, saves initial state to SQLite, and logs the start.
Runs first in the SequentialAgent pipeline.
"""
from google.adk.agents import Agent
from google.adk.tools import ToolContext
from tools.product_memory_tools import generate_product_id, save_product_state, log_step
from tools.system_env_tools import detect_system_environment

from agents._shared.model import get_model
from agents._shared.mcp_hub import mcp_hub
from agents._shared.model import FAST


def _save_to_state(key: str, value: str, tool_context: ToolContext) -> str:
    """Save a value to session state so downstream agents can read it."""
    tool_context.state[key] = value
    return f"Saved '{key}' to session state"


INSTRUCTION = """\
You initialize the product pipeline. Do these steps IN ORDER:

1. Call generate_product_id() to get a new UUID.
2. Extract the product name from the user's requirement (use PascalCase, e.g. "SpaceMissionControl").
3. Call save_product_state(product_id=<uuid>, product_name=<name>, status="running").
4. Call log_step(product_id=<uuid>, step="start", message=<the user's original requirement>).
5. Call detect_system_environment() to scan the machine for installed runtimes, databases, and tools.
6. Call _save_to_state(key="system_environment", value=<the full JSON result from detect_system_environment>).
7. Call _save_to_state(key="product_id", value=<uuid>) to make it available to downstream agents.
8. Output ONLY the product_id UUID as plain text. Nothing else.
"""

_mcp_tools = mcp_hub.get_toolsets(["docs", "duckduckgo", "web_search"])

setup_agent = Agent(
    model=get_model(FAST),
    name="setup_agent",
    description="Initializes product pipeline: generates product_id, saves initial state, logs start.",
    instruction=INSTRUCTION,
    output_key="setup_output",
    tools=[generate_product_id, save_product_state, log_step, _save_to_state, detect_system_environment,
        *_mcp_tools,],
)
