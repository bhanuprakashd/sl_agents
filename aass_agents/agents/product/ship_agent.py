# aass_agents/agents/product/ship_agent.py
"""
Ship Agent — finalizes the product pipeline run.

Reads all state from previous agents, persists final state to SQLite,
saves learned skills for future builds, and returns the final JSON summary.
"""
from google.adk.agents import Agent
from google.adk.tools import ToolContext

from agents._shared.model import get_model, FAST
from tools.product_memory_tools import save_product_state, log_step
from tools.skill_memory import save_learned_skill, update_skill_quality_from_feedback
from tools.claude_code_tools import open_in_browser


def read_state(key: str, tool_context: ToolContext) -> str:
    """Read a value from session state. Use to get build_output, qa_output, prd_output, etc."""
    value = tool_context.state.get(key)
    if value is None:
        return f"No value found in state for key '{key}'"
    return str(value)


INSTRUCTION = """\
You finalize the product pipeline. Do these steps IN ORDER:

1. Read all state:
   - read_state("product_id") or read_state("setup_output") for the product_id
   - read_state("prd_output") for the PRD
   - read_state("architecture_output") for the architecture
   - read_state("build_output") for the build result
   - read_state("qa_output") for the QA report

2. Determine final status from build and QA results:
   - If QA passed → "shipped"
   - If build has URL but QA failed → "shipped_with_issues"
   - If build completed but no URL → "built"
   - Otherwise → "failed"

3. Save final state:
   - save_product_state(product_id, status=<final_status>, qa_report=<qa_output>)

4. Save learned skill for future builds:
   - save_learned_skill(product_id, product_name, prd_summary, architecture_summary, build_result_summary)

5. Log completion:
   - log_step(product_id, step="complete", message=<one-line summary>)

6. If there's a live URL, call open_in_browser(url).

7. Output the final JSON summary (no markdown, no code fences, just raw JSON):
{
  "status": "<final_status>",
  "product_id": "<uuid>",
  "live_url": "<url or null>",
  "product_name": "",
  "one_liner": "",
  "target_user": "",
  "tech_stack": "",
  "core_features": [],
  "build_report": {
    "phases_completed": [],
    "fix_iterations": 0,
    "qa_passed": false,
    "feedback_rounds": 0
  }
}
"""

ship_agent = Agent(
    model=get_model(FAST),
    name="ship_agent",
    description="Finalizes pipeline: persists state, saves learned skills, returns final JSON summary.",
    instruction=INSTRUCTION,
    output_key="ship_output",
    tools=[
        read_state,
        save_product_state, log_step,
        save_learned_skill, update_skill_quality_from_feedback,
        open_in_browser,
    ],
)
