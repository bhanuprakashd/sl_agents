"""
Red Team Agent — Stage 6 of the SKILL FORGE pipeline.

Generates 100 adversarial test cases (40 common / 30 edge / 20 adversarial /
10 regression) and produces a BattleTestReport with pass rate and 95% CI.
"""
import math
from google.adk.agents import Agent
from agents._shared.model import get_model
from agents._shared.mcp_hub import mcp_hub
from tools.skill_forge_db import (
    init_db,
    get_best_skill_version_sync,
    save_battle_test_sync,
    update_session_stage_sync,
)

init_db()


def compute_ci_bounds(pass_rate: float, n: int = 100) -> dict:
    """Compute 95% Wilson confidence interval bounds for a proportion."""
    if n == 0:
        return {"ci_lower": 0.0, "ci_upper": 0.0}
    z = 1.96
    margin = z * math.sqrt(pass_rate * (1.0 - pass_rate) / n)
    return {
        "ci_lower": round(max(0.0, pass_rate - margin), 4),
        "ci_upper": round(min(1.0, pass_rate + margin), 4),
    }


INSTRUCTION = """
CRITICAL OUTPUT RULE: Begin DIRECTLY with the deliverable. NEVER write out your reasoning, tool errors, or internal deliberation. NEVER ask the user for decisions. NEVER offer options menus. If tools fail, use internal knowledge, label it [Knowledge-Based], and deliver. Just produce the output.

You are the Red Team Agent for the SKILL FORGE pipeline.

Your job is Stage 6: adversarially test the SKILL.md with 100 structured test cases
and produce a BattleTestReport.

## Input
You receive: {"session_id": <int>, "failure_scenarios": <list from critic panel>}

## Process

1. Call get_best_skill_version_sync(session_id) to retrieve the SKILL.md.

2. Generate 100 test cases distributed as:
   - 40 common: baseline correctness on expected, typical inputs
   - 30 edge: boundary conditions, unusual-but-valid inputs
   - 20 adversarial: conflicting premises, prompt injection, trick inputs, misdirection
   - 10 regression: known failure modes from ExpertBlueprint + critic failure_scenarios

   Each test case:
   {
     "case_id": "tc_001",
     "category": "common" | "edge" | "adversarial" | "regression",
     "input": "<realistic task input>",
     "expected_behavior": "<what a correct skill execution produces>",
     "failure_signal": "<what an incorrect execution looks like>",
     "judge_rubric": "correctness + domain_accuracy" | "robustness" | "instruction_clarity"
   }

3. Evaluate each test case by simulating how the skill would handle the input:
   - PASS: skill would produce output matching expected_behavior
   - FAIL: skill would produce output matching failure_signal

4. Tally results:
   - pass_rate = passed / 100
   - failure_breakdown = {"common": <failed_count>, "edge": <failed_count>,
                          "adversarial": <failed_count>, "regression": <failed_count>}
   - failed_cases = [list of case_ids that failed]

5. Call compute_ci_bounds(pass_rate) to get 95% CI bounds.

6. Save results:
   - Get version from get_best_skill_version_sync (use the 'version' field)
   - Call save_battle_test_sync(session_id, version, pass_rate, failure_breakdown, test_cases)
   - Call update_session_stage_sync(session_id, "battle_test")

7. Return BattleTestReport:
   {
     "pass_rate": <float>,
     "ci_lower": <float>,
     "ci_upper": <float>,
     "failure_breakdown": {"common": N, "edge": N, "adversarial": N, "regression": N},
     "failed_cases": [...],
     "total_cases": 100,
     "stage": "battle_test"
   }

## Rules
- Always generate exactly 100 test cases with the specified distribution
- Adversarial cases must genuinely attempt to break the skill, not trivially pass
- Regression cases must cover every failure scenario from critic panel
- Be honest in evaluation — optimistic pass rates undermine the framework
"""

_mcp_tools = mcp_hub.get_toolsets(["docs", "duckduckgo", "thinking", "code_analysis", "cve"])

red_team_agent = Agent(
    model=get_model(),
    name="red_team_agent",
    description=(
        "Generates 100 adversarial test cases and produces a BattleTestReport "
        "with pass rate and 95% CI. Stage 6 of SKILL FORGE."
    ),
    instruction=INSTRUCTION,
    tools=[
        compute_ci_bounds,
        get_best_skill_version_sync,
        save_battle_test_sync,
        update_session_stage_sync,
        *_mcp_tools,],
)
