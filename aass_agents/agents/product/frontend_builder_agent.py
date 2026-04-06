# aass_agents/agents/product/frontend_builder_agent.py
"""
Frontend Builder Agent — generates React (Vite) UI and deploys to Vercel.

Reads PRD + architecture from session state (pipeline mode) or SQLite (standalone).
Runs AFTER backend_builder so backend_url is available in state.
"""
import os
from google.adk.agents import Agent
from google.adk.tools import ToolContext
from tools.product_memory_tools import save_product_state, recall_product_state, log_step
from tools.github_tools import push_file
from tools.vercel_tools import trigger_deploy, get_deployment_url
from tools.code_gen_tools import generate_code

from agents._shared.model import get_model
from agents._shared.mcp_hub import mcp_hub


def read_state(key: str, tool_context: ToolContext) -> str:
    """Read a value from session state. Use to get prd_output, architecture_output, product_id, backend_output, etc."""
    value = tool_context.state.get(key)
    if value is None:
        return f"No value found in state for key '{key}'"
    return str(value)


INSTRUCTION = """
CRITICAL OUTPUT RULE: Begin DIRECTLY with the deliverable. NEVER write out your reasoning, tool errors, or internal deliberation. NEVER ask the user for decisions. NEVER offer options menus. If tools fail, use internal knowledge, label it [Knowledge-Based], and deliver. Just produce the output.

You are a Frontend Builder agent. You generate a React (Vite) UI and deploy it to Vercel.

## Your Process

1. Read state: call read_state("product_id"), read_state("prd_output"), read_state("architecture_output").
   Also call read_state("backend_output") to get backend_url for API connection.
   If state is empty, fall back to `recall_product_state`.
2. Generate frontend files using `generate_code`:
   - package.json (react, react-dom, vite, tailwindcss)
   - vite.config.js
   - tailwind.config.js
   - postcss.config.js
   - index.html
   - src/main.jsx (React entry point)
   - src/App.jsx (main app component)
   - src/index.css (Tailwind directives)
   - Key component files from architecture.file_tree
3. Push each file under /frontend/ using `push_file`
4. Trigger Vercel deployment: call `trigger_deploy` with vercel_project_id
5. Poll `get_deployment_url` until non-empty (max 5 minutes, 30s intervals)
6. Save frontend_url to product state
7. Call `log_step` with step="frontend" and frontend_url
8. Output the frontend build result including frontend_url.

## Code Generation Guidelines
- Use React with Vite (src/ structure, JSX files)
- Use Tailwind CSS for all styling — no custom CSS files except index.css
- VITE_API_URL env var should point to backend_url from state
- Include a basic loading state for async operations
- Keep it functional — no animations or polish for v1
- Retry budget: if build fails, regenerate and push up to 3 times total
"""

# MCP tools: docs, npm_search, js_sandbox, github, duckduckgo,
# image_gen (AI mockups/icons), charts (data viz), svg (vector graphics), diagrams (mermaid)
_mcp_tools = mcp_hub.get_toolsets([
    "docs", "npm_search", "js_sandbox", "github", "duckduckgo",
    "image_gen", "charts", "svg", "diagrams",
    # New: design, a11y, code quality, visual QA
    "colors", "a11y", "html_valid", "css_analyze", "bundle",
    "placeholder", "fonts", "screenshot", "eslint", "prettier",
])

frontend_builder_agent = Agent(
    model=get_model(),
    name="frontend_builder_agent",
    description="Generates React (Vite) + Tailwind UI and deploys it to Vercel.",
    instruction=INSTRUCTION,
    output_key="frontend_output",
    tools=[
        read_state,
        save_product_state, recall_product_state, log_step,
        push_file, trigger_deploy, get_deployment_url,
        generate_code,
        *_mcp_tools,
    ],
)
