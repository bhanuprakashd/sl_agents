# aass_agents/agents/product/architect_critic_agent.py
"""
Architect Critic Agent — reviews architecture JSON and either approves or requests changes.

Used inside a LoopAgent with architect_agent for iterative refinement.
Sets escalate=True when the architecture meets quality standards.
"""
from google.adk.agents import Agent
from google.adk.tools import ToolContext

from agents._shared.model import get_model
from agents._shared.mcp_hub import mcp_hub, STD


def read_state(key: str, tool_context: ToolContext) -> str:
    """Read a value from session state."""
    value = tool_context.state.get(key)
    if value is None:
        return f"No value found in state for key '{key}'"
    return str(value)


def approve_architecture(tool_context: ToolContext) -> dict:
    """Call this when the architecture passes all quality checks. Exits the refinement loop."""
    tool_context.actions.escalate = True
    return {"status": "approved", "message": "Architecture meets quality standards."}


INSTRUCTION = """\
You are an architecture critic. You review the architecture JSON produced by architect_agent
and either approve it or request specific improvements.

## Process

1. Read the current architecture: call read_state("architecture_output")
2. Also read the PRD for context: call read_state("prd_output")
3. Evaluate against these criteria:

   **MUST PASS (block on failure):**
   - All PRD features have corresponding API endpoints
   - Database schema covers all data models from PRD
   - File tree has both frontend and backend files
   - No banned tech (Supabase, Firebase, Auth0, AWS, Next.js, Express)
   - Stack matches PRD tech_preferences if specified
   - Environment constraints section is present

   **SHOULD PASS (warn but don't block):**
   - Design system has all color fields populated
   - Research findings include at least 1 analyzed repo
   - API endpoints follow RESTful conventions
   - Database schema includes indexes on foreign keys

4. Decision:
   - If ALL must-pass criteria are met → call approve_architecture() to exit the loop
   - If any must-pass criteria fail → output a JSON critique:
     {
       "approved": false,
       "issues": [{"severity": "must_fix", "field": "...", "problem": "...", "suggestion": "..."}],
       "warnings": [{"field": "...", "problem": "...", "suggestion": "..."}]
     }

The architect_agent will read your critique from state and revise.
Do NOT call approve_architecture unless ALL must-pass criteria are satisfied.
"""

_mcp_tools = mcp_hub.get_toolsets(["docs", "github", "duckduckgo", "diagrams", "drawio", "cve", "sec_audit"])

architect_critic_agent = Agent(
    model=get_model(STD),
    name="architect_critic_agent",
    description="Reviews architecture JSON against PRD requirements. Approves or requests changes.",
    instruction=INSTRUCTION,
    output_key="architecture_critique",
    tools=[read_state, approve_architecture,
        *_mcp_tools,],
)
