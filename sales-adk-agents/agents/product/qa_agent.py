# sales-adk-agents/agents/qa_agent.py
"""
QA Agent — smoke tests the live deployment using HTTP tools and gstack browse binary.
"""
import os
from google.adk.agents import Agent
from tools.product_memory_tools import save_product_state, recall_product_state, log_step
from tools.http_tools import smoke_test, health_check, auth_smoke_test

MODEL = os.getenv("MODEL_ID", "gemini-2.0-flash")

# Path to gstack headless browser binary (built from deer-flow/skills/gstack)
_GSTACK_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "deer-flow", "skills", "gstack")
_BROWSE_BIN = os.path.join(_GSTACK_DIR, "browse", "dist", "browse")

INSTRUCTION = f"""
You are a QA agent. You smoke test the live deployment.

## Tools Available
- HTTP tools: `smoke_test`, `health_check`, `auth_smoke_test` — fast pass/fail checks
- gstack browse binary: `{_BROWSE_BIN}` — headless Chromium for visual verification
  Use bash to run: `{_BROWSE_BIN} goto <url> && {_BROWSE_BIN} snapshot -i`
  Take screenshots: `{_BROWSE_BIN} screenshot /tmp/qa-screenshot.png`

## Your Process

1. Call `recall_product_state` to get frontend_url, backend_url, PRD
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

qa_agent = Agent(
    model=MODEL,
    name="qa_agent",
    description="Smoke tests the live deployment: root URL, health endpoint, auth flow.",
    instruction=INSTRUCTION,
    tools=[
        save_product_state, recall_product_state, log_step,
        smoke_test, health_check, auth_smoke_test,
    ],
)
