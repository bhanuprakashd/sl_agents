# aass_agents/agents/pm_agent.py
"""
PM Agent — converts raw requirement into a structured PRD.
Uses DeerFlow (via MCP research_server) for competitor research.
Uses claude-haiku-4-5 via ADK (cost-efficient for structured JSON output).
"""
import os
from google.adk.agents import Agent
from tools.product_memory_tools import save_product_state, recall_product_state, log_step

from agents._shared.model import get_model
INSTRUCTION = """
You are a Product Manager agent. Your job is to convert a raw product requirement into a
structured PRD (Product Requirements Document).

## Your Process

1. Use `search_product_web` and `search_news` to research competitors and market trends
3. Generate a PRD as a JSON object with these exact fields:
   - product_name: short, memorable name (no spaces, PascalCase)
   - one_liner: one sentence describing the product
   - target_user: who it is for
   - core_features: list of max 5 features for v1 (keep it shippable)
   - data_model: list of main entities with key fields
   - acceptance_criteria: list of 3-5 testable criteria
   - product_type: one of [full-stack SaaS, API-heavy backend, simple landing + auth, data-heavy app]
4. Call `save_product_state` with the PRD
5. Call `log_step` with step="pm" and a summary of the PRD

## Constraints
- v1 scope only — if the requirement is too large, cut features until it is shippable in one run
- product_type MUST be one of the four listed above — this drives the stack decision downstream
- data_model entities should be realistic for a free-tier single database
"""

from google.adk.tools.mcp_tool.mcp_toolset import McpToolset, StdioConnectionParams, StdioServerParameters

_HERE = os.path.dirname(os.path.abspath(__file__))
_RESEARCH_SERVER = os.path.abspath(os.path.join(_HERE, "..", "..", "mcp-servers", "gtm", "research_server.py"))

# DeerFlow research tools come from the MCP research_server process
_research_mcp = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command="python",
            args=[_RESEARCH_SERVER],
            env={**os.environ},
        )
    )
)

_MEDIUM_MCP_PATH = os.path.abspath(os.getenv("MEDIUM_MCP_PATH") or os.path.join(_HERE, "..", "..", "medium-mcp-server"))
_medium_mcp = None
if os.path.isfile(os.path.join(_MEDIUM_MCP_PATH, "dist", "index.js")):
    _medium_mcp = McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command="node",
                args=[os.path.join(_MEDIUM_MCP_PATH, "dist", "index.js")],
                cwd=_MEDIUM_MCP_PATH,
                env={**os.environ},
            )
        )
    )

pm_agent = Agent(
    model=get_model(),
    name="pm_agent",
    description="Converts a raw product requirement into a structured PRD using market research.",
    instruction=INSTRUCTION,
    tools=[t for t in [
        save_product_state, recall_product_state, log_step,
        _research_mcp,
        _medium_mcp,
    ] if t is not None],
)
