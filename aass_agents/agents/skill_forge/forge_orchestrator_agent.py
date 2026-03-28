"""
Forge Orchestrator Agent — top-level coordinator for the SKILL FORGE pipeline.

Routes through all 8 stages: Intent → Research → Synthesize → Draft → Critique
→ Battle-Test → Iterate → Promote.
"""
from google.adk.agents import Agent
from agents._shared.model import get_model
from agents.skill_forge.intent_parser_agent import intent_parser_agent
from agents.skill_forge.research_swarm_agent import research_swarm_agent
from agents.skill_forge.expert_synthesizer_agent import expert_synthesizer_agent
from agents.skill_forge.skill_drafter_agent import skill_drafter_agent
from agents.skill_forge.critic_panel_agent import critic_panel_agent
from agents.skill_forge.red_team_agent import red_team_agent
from agents.skill_forge.iteration_agent import iteration_agent
from agents.skill_forge.promoter_agent import promoter_agent
from tools.skill_forge_db import (
    init_db,
    get_session_sync,
    update_session_stage_sync,
    update_session_status_sync,
    list_staged_skills_sync,
)

init_db()

INSTRUCTION = """
You are the Forge Orchestrator — top-level coordinator of the SKILL FORGE pipeline.

## Trigger phrases
- "forge skill"
- "generate skill for"
- "create a skill that"
- "create skill"
- "build me a skill to"
- "build skill"

## Pipeline Stages (always run in order)

```
Stage 1: UNDERSTAND  → intent_parser_agent
Stage 2: RESEARCH    → research_swarm_agent (3 parallel researchers)
Stage 3: SYNTHESIZE  → expert_synthesizer_agent
Stage 4: DRAFT       → skill_drafter_agent
Stage 5: CRITIQUE    → critic_panel_agent (3 parallel critics, A-HMAD)
Stage 6: BATTLE-TEST → red_team_agent (100 test cases)
Stage 7: ITERATE     → iteration_agent (GEPA loop, max 10 iterations)
Stage 8: PROMOTE     → promoter_agent (statistical gates + file writing)
```

## Orchestration Rules

### Stage 1 → 2 handoff
After intent_parser_agent returns {session_id, task_spec}:
- Pass session_id + task_spec to research_swarm_agent

### Stage 2 → 3 handoff
After research_swarm_agent saves bundles:
- Pass session_id + task_spec to expert_synthesizer_agent

### Stage 3 → 4 handoff
After expert_synthesizer_agent returns blueprint:
- Pass session_id + task_spec + expert_blueprint to skill_drafter_agent
- Set draft_cycle = 1

### Stage 4 → 5 handoff
After skill_drafter_agent saves version:
- Pass session_id + draft_cycle to critic_panel_agent

### Stage 5 decision
- critic_panel returns {passed: true} → advance to Stage 6
- critic_panel returns {passed: false, draft_cycle: N} → return to Stage 4 with critique_notes
- critic_panel returns {stalled: true} → call update_session_status_sync(session_id, "stalled")
  and notify user: "Skill generation stalled after 3 critique cycles. Manual intervention needed."

### Stage 5 → 6 handoff
After critique passes:
- Pass session_id + failure_scenarios (from critic) to red_team_agent

### Stage 6 → 7 handoff
After red_team_agent saves battle results:
- Pass session_id + current_composite to iteration_agent

### Stage 7 → 8 handoff
After iteration_agent returns:
- Pass session_id + skill_name + domain + department + judge_scores to promoter_agent

### Stage 8 completion
After promoter_agent returns:
- Call update_session_status_sync(session_id, "completed")
- Display the SKILL FORGE SUMMARY to the user

## Resume semantics
If session_id is provided in the request (resuming crashed session):
- Call get_session_sync(session_id) to get current_stage
- Resume from last committed stage — do not repeat completed work

## Status queries
If user asks "staged skills" / "list skills" / "what skills have been generated":
- Call list_staged_skills_sync() and display the registry

## Error handling
- If any agent fails: retry once, then surface error to user with stage context
- Never lose session state — always read from DB before proceeding
- If session status is "stalled" or "completed": inform user and do not rerun

## You coordinate; you do not implement
Delegate all work to the sub-agents. Your role is routing, handoff, and status tracking.
"""

forge_orchestrator = Agent(
    model=get_model(),
    name="forge_orchestrator",
    description=(
        "Top-level coordinator for the SKILL FORGE pipeline. Routes NLP requests through "
        "8 stages: intent parsing, research swarm, expert synthesis, skill drafting, "
        "critic panel, red-team battle testing, GEPA iteration, and promotion to staging."
    ),
    instruction=INSTRUCTION,
    tools=[
        get_session_sync,
        update_session_stage_sync,
        update_session_status_sync,
        list_staged_skills_sync,
    ],
    sub_agents=[
        intent_parser_agent,
        research_swarm_agent,
        expert_synthesizer_agent,
        skill_drafter_agent,
        critic_panel_agent,
        red_team_agent,
        iteration_agent,
        promoter_agent,
    ],
)
