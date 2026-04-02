# aass_agents/agents/product/builder_agent.py
"""
Builder Agent — reads PRD + architecture from state, builds the application.

Uses build_with_feedback_loop for multi-phase iterative builds.
Runs after pm_agent and architect_agent in the SequentialAgent pipeline.
"""
from google.adk.agents import Agent
from google.adk.tools import ToolContext

from agents._shared.model import get_model
from agents._shared.context_rules import ERROR_PRESERVATION_RULE
from tools.product_memory_tools import save_product_state, log_step
from tools.claude_code_tools import (
    build_and_run, build_review_improve, build_with_feedback_loop, open_in_browser,
)
from tools.skill_memory import find_similar_skills, save_learned_skill
from tools.human_feedback_loop import get_feedback_patterns


def read_state(key: str, tool_context: ToolContext) -> str:
    """Read a value from session state. Use to get prd_output, architecture_output, product_id, etc."""
    value = tool_context.state.get(key)
    if value is None:
        return f"No value found in state for key '{key}'"
    return str(value)


INSTRUCTION = f"""\
You build the application from the PRD and architecture. Execute autonomously. No questions.

## Process

1. Read state: call read_state("product_id") to get the product_id (saved by setup_agent as "setup_output" or "product_id").
   Also call read_state("prd_output") and read_state("architecture_output").

2. Learn: call find_similar_skills(product_name, prd_summary) AND get_feedback_patterns().
   Use proven patterns and common pitfalls to improve build prompts.

3. Parse the PRD and architecture JSON. Extract:
   - product_name (use as project_name slug, lowercase with hyphens)
   - All features, endpoints, data model, design system
   - research_findings.patterns_to_reuse and top repo URLs from architecture

4. Build: call build_with_feedback_loop with these args:
   - project_name: lowercase-hyphenated product name
   - scaffold_task: Detailed prompt covering tech stack, deps, config, file tree, DB schema+seed,
     auth (signup/login/JWT/middleware), layout+nav+routing, design system colors. NO dev server.
     Prepend research_findings patterns and repo URLs.
   - feature_task: For EACH PRD feature: name, user story, priority, API endpoints, DB queries,
     frontend pages, components, validation, error handling. Quality: form validation, loading spinners,
     empty states, error toasts, typed code, realistic seed data. NO dev server.
     Prepend research_findings patterns and repo URLs.
   - polish_task: Design system colors+theme, branding, dashboard stats, form consistency,
     sortable tables, active nav, empty/loading/error states, responsive, micro-interactions,
     typography scale. START dev server after.
     Prepend research_findings patterns and repo URLs.
   - product_id: the product_id from state
   - prd: the full PRD JSON string

5. After build completes, parse the result JSON. Save to SQLite:
   - call save_product_state(product_id, frontend_url=<url from result>)
   - call log_step(product_id, step="build", message=<summary of phases completed>)

6. Output the build result JSON. Include the URL if available.

{ERROR_PRESERVATION_RULE}
"""

builder_agent = Agent(
    model=get_model(),
    name="builder_agent",
    description="Builds the application using PRD and architecture from session state via build_with_feedback_loop.",
    instruction=INSTRUCTION,
    output_key="build_output",
    tools=[
        read_state,
        build_and_run, build_review_improve, build_with_feedback_loop, open_in_browser,
        find_similar_skills, save_learned_skill, get_feedback_patterns,
        save_product_state, log_step,
    ],
)
