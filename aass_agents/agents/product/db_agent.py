# aass_agents/agents/product/db_agent.py
"""
DB Agent — generates SQLite schema and initializes the local database.

Reads PRD + architecture from session state (pipeline mode) or SQLite (standalone).
"""
import os
from google.adk.agents import Agent
from google.adk.tools import ToolContext
from tools.product_memory_tools import save_product_state, recall_product_state, log_step
from tools.code_gen_tools import generate_db_schema

from agents._shared.model import get_model, FAST
from agents._shared.mcp_hub import mcp_hub


def read_state(key: str, tool_context: ToolContext) -> str:
    """Read a value from session state. Use to get prd_output, architecture_output, product_id, etc."""
    value = tool_context.state.get(key)
    if value is None:
        return f"No value found in state for key '{key}'"
    return str(value)


INSTRUCTION = """
CRITICAL OUTPUT RULE: Begin DIRECTLY with the deliverable. NEVER write out your reasoning, tool errors, or internal deliberation. NEVER ask the user for decisions. NEVER offer options menus. If tools fail, use internal knowledge, label it [Knowledge-Based], and deliver. Just produce the output.

You are a Database agent. You generate the SQLite schema and migration script.

## Your Process

1. Read state: call read_state("product_id"), read_state("prd_output"), and read_state("architecture_output").
   If state is empty, fall back to `recall_product_state`.
2. Generate SQLite-compatible CREATE TABLE statements from data_model in PRD using `generate_db_schema`
3. Save `database_url` as "sqlite+aiosqlite:///./app.db" to product state via `save_product_state`
4. Call `log_step` with step="db" and "SQLite schema generated — migration script ready"
5. Output the schema SQL as your final result.

## SQL Guidelines
- Always include: id (INTEGER PRIMARY KEY AUTOINCREMENT), created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
- Use TEXT for strings
- Add basic indexes on foreign keys
- Keep it simple — no stored procedures, no triggers for v1
- SQLite compatible syntax only (no UUID type, no NOW(), no SERIAL)
"""

# MCP tools: sqlite, docs, github (schema patterns), duckduckgo
_mcp_tools = mcp_hub.get_toolsets(["sqlite", "docs", "github", "duckduckgo"])

db_agent = Agent(
    model=get_model(FAST),
    name="db_agent",
    description="Generates SQLite schema and initializes the local database.",
    instruction=INSTRUCTION,
    output_key="db_output",
    tools=[
        read_state,
        save_product_state, recall_product_state, log_step,
        generate_db_schema,
        *_mcp_tools,
    ],
)
