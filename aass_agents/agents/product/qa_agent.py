# aass_agents/agents/qa_agent.py
"""
QA Agent — smoke tests the live deployment using HTTP tools and gstack browse binary.
Uses ADK output_key to auto-save QA report to session state.
"""
import os
from google.adk.agents import Agent
from google.adk.tools import ToolContext
from tools.product_memory_tools import save_product_state, recall_product_state, log_step
from tools.http_tools import smoke_test, health_check, auth_smoke_test

from agents._shared.model import get_model, FAST
from agents._shared.mcp_hub import mcp_hub


def read_state(key: str, tool_context: ToolContext) -> str:
    """Read a value from session state. Use to get build_output, prd_output, product_id, etc."""
    value = tool_context.state.get(key)
    if value is None:
        return f"No value found in state for key '{key}'"
    return str(value)
# Path to gstack headless browser binary (built from deer-flow/skills/gstack)
_GSTACK_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "deer-flow", "skills", "gstack")
_BROWSE_BIN = os.path.join(_GSTACK_DIR, "browse", "dist", "browse")

INSTRUCTION = f"""
You are a QA agent. You smoke test the live deployment.
Your response will be automatically saved to session state via output_key.

## Tools Available
- HTTP tools: `smoke_test`, `health_check`, `auth_smoke_test` — fast pass/fail checks
- State tools: `read_state` — read build_output, prd_output, product_id from session state
- gstack browse binary: `{_BROWSE_BIN}` — headless Chromium for visual verification
  Use bash to run: `{_BROWSE_BIN} goto <url> && {_BROWSE_BIN} snapshot -i`
  Take screenshots: `{_BROWSE_BIN} screenshot /tmp/qa-screenshot.png`

## Your Process

1. Call read_state("build_output") to get the build result (contains URL).
   Also call read_state("prd_output") for PRD and read_state("setup_output") or read_state("product_id") for the product_id.
   Fall back to recall_product_state if state keys are empty.
2. Run these tests IN ORDER — stop on first failure:

   Test 1: Frontend root (HTTP)
   - `smoke_test([frontend_url])` → must return passed=True
   - If fail: report "Frontend root URL returned HTTP [code]"

   Test 2: Backend health (HTTP)
   - `health_check(backend_url)` → must return passed=True
   - If fail: report "Backend health check failed: [error]"

   Test 3: Visual check (gstack browse)
   - Run: `{_BROWSE_BIN} goto <frontend_url>`
   - Run: `{_BROWSE_BIN} screenshot /tmp/qa-screenshot.png`
   - Check for JS console errors: `{_BROWSE_BIN} console --errors`
   - Note any visible errors or broken layout

   Test 4: Auth flow (only if PRD acceptance_criteria mentions auth)
   - `auth_smoke_test(frontend_url)` → must return passed=True (200, 201, or 409)

3. Build qa_report:
   {{
     "passed": true/false,
     "tests": [{{"name": "...", "passed": true/false, "detail": "..."}}],
     "screenshot": "/tmp/qa-screenshot.png",
     "failure_reason": "..." or null
   }}
4. Call `save_product_state` with qa_report
5. Call `log_step` with step="qa" and summary: PASSED or FAILED + reason

## On Failure
Return the qa_report to product_orchestrator — it will decide whether to retry.
Do NOT retry yourself.
"""

# MCP tools: browser, fetch, js_sandbox, cve, github (test patterns), duckduckgo
_mcp_tools = mcp_hub.get_toolsets(["browser", "fetch", "js_sandbox", "cve", "github", "duckduckgo"])

qa_agent = Agent(
    model=get_model(FAST),  # QA is simple pass/fail checks, doesn't need deep reasoning
    name="qa_agent",
    description="Smoke tests the live deployment: root URL, health endpoint, auth flow, visual checks via browser.",
    instruction=INSTRUCTION,
    output_key="qa_output",  # Auto-save QA report to state["qa_output"]
    tools=[
        read_state,
        save_product_state, recall_product_state, log_step,
        smoke_test, health_check, auth_smoke_test,
        *_mcp_tools,
    ],
)
