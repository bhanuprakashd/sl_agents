# aass_agents/agents/product/backend_builder_agent.py
"""
Backend Builder Agent — generates Python/FastAPI backend and deploys to Railway.
Uses claude-sonnet-4-6 via code_gen_tools for code generation.

Reads PRD + architecture from session state (pipeline mode) or SQLite (standalone).
"""
import os
from google.adk.agents import Agent
from google.adk.tools import ToolContext
from tools.product_memory_tools import save_product_state, recall_product_state, log_step
from tools.github_tools import push_file
from tools.railway_tools import deploy_from_github, get_service_url
from tools.code_gen_tools import generate_code

from agents._shared.model import get_model
from agents._shared.mcp_hub import mcp_hub


def read_state(key: str, tool_context: ToolContext) -> str:
    """Read a value from session state. Use to get prd_output, architecture_output, product_id, etc."""
    value = tool_context.state.get(key)
    if value is None:
        return f"No value found in state for key '{key}'"
    return str(value)


INSTRUCTION = """
CRITICAL OUTPUT RULE: Begin DIRECTLY with the deliverable. NEVER write out your reasoning, tool errors, or internal deliberation. NEVER ask the user for decisions. NEVER offer options menus. If tools fail, use internal knowledge, label it [Knowledge-Based], and deliver. Just produce the output.

You are a Backend Builder agent. You generate a Python/FastAPI backend and deploy it.

## Your Process

1. Read state: call read_state("product_id"), read_state("prd_output"), and read_state("architecture_output").
   If state is empty, fall back to `recall_product_state`.
2. Generate each backend file using `generate_code`:
   - main.py, requirements.txt, Dockerfile, routes/*.py, models/*.py
3. Push each file to the repo using `push_file` under /backend/
4. Trigger Railway deployment:
   - Call `deploy_from_github` with repo_full_name
   - Save service_id to product state (needed by devops_agent for env var injection)
5. Wait for deploy (poll `get_service_url` until non-empty, max 5 minutes, 30s intervals)
6. Save backend_url to product state
7. Call `log_step` with step="backend" and backend_url
8. Output the backend build result including backend_url.

## Code Generation Guidelines
- Always use Python + FastAPI (no Node.js backends)
- Include health endpoint at GET /health returning {"status": "ok"}
- Include CORS middleware for the frontend domain
- All endpoints should use Pydantic models for request/response
- Use SQLite with SQLAlchemy + aiosqlite for database
- DATABASE_URL defaults to "sqlite+aiosqlite:///./app.db"
- Retry budget: if deploy fails, retry generate + push up to 3 times total

## Context to pass to generate_code
Pass the full PRD and architecture JSON as context so the LLM knows the data model and endpoints.
"""

# MCP tools: docs, packages, cve, github (code patterns), duckduckgo (web search)
_mcp_tools = mcp_hub.get_toolsets([
    "docs",
    "packages",
    "cve",
    "github",
    "duckduckgo",
    "openapi",
    "py_lint",
    "pytest",
    "sec_audit",
])

backend_builder_agent = Agent(
    model=get_model(),
    name="backend_builder_agent",
    description="Generates Python/FastAPI backend and deploys it to Railway.",
    instruction=INSTRUCTION,
    output_key="backend_output",
    tools=[
        read_state,
        save_product_state, recall_product_state, log_step,
        push_file, deploy_from_github, get_service_url,
        generate_code,
        *_mcp_tools,
    ],
)
