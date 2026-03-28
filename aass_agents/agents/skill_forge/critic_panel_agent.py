"""
Critic Panel Agent — Stage 5 of the SKILL FORGE pipeline.

Implements A-HMAD (heterogeneous multi-agent debate) with 3 critic sub-agents.
Computes composite score and routes back to drafter if < 7.5 (max 3 cycles).
"""
from google.adk.agents import Agent
from agents._shared.model import get_model
from tools.skill_forge_db import (
    init_db,
    get_best_skill_version_sync,
    save_skill_version_sync,
    update_session_stage_sync,
)

init_db()

_DOMAIN_EXPERT_CRITIC_INSTRUCTION = """
You are the Domain Expert Critic in the SKILL FORGE critic panel.

Your lens: factual accuracy and completeness from a domain expert perspective.

Evaluate the SKILL.md you are given:
1. Check factual accuracy: are all claims correct?
2. Check completeness: is critical expert knowledge missing?
3. Check for outdated techniques or superseded best practices
4. Check domain-specific terminology correctness
5. Identify any dangerous oversimplifications

Score 1-10 on domain correctness (10 = publishable by domain authority).

Output:
{
  "critic_type": "domain_expert",
  "score": <float 1-10>,
  "feedback": "<detailed assessment>",
  "suggestions": ["specific correction 1", "specific correction 2", ...]
}
"""

_INSTRUCTION_QUALITY_CRITIC_INSTRUCTION = """
You are the Instruction Quality Critic in the SKILL FORGE critic panel.

Your lens: clarity, actionability, and usability of the instructions.

Evaluate the SKILL.md you are given:
1. Read as a first-time user: can you follow every step without prior domain knowledge?
2. Identify ambiguous verbs (e.g. "consider", "think about" — replace with concrete actions)
3. Verify step ordering is logical and each step is executable
4. Check example alignment: do examples actually demonstrate what the instructions say?
5. Check for internal contradictions between sections

Score 1-10 on instruction quality (10 = perfectly clear to a new user).

Output:
{
  "critic_type": "instruction_quality",
  "score": <float 1-10>,
  "feedback": "<detailed assessment>",
  "suggestions": ["specific rewrite 1", "specific rewrite 2", ...]
}
"""

_EDGE_CASE_CRITIC_INSTRUCTION = """
You are the Edge Case Critic in the SKILL FORGE critic panel.

Your lens: robustness — what breaks the skill under adversarial or boundary conditions.

Evaluate the SKILL.md you are given:
1. Generate 10 adversarial scenarios:
   - Ambiguous or conflicting inputs
   - Boundary conditions (minimal/maximal inputs)
   - Prompt injection attempts
   - Domain-adjacent inputs that could be misrouted
   - Missing or incomplete context

2. Test each scenario against the skill's instructions
3. Identify failure modes not covered by the skill's "Failure Modes" section

Score 1-10 on robustness (10 = handles all 10 adversarial scenarios gracefully).

Output:
{
  "critic_type": "edge_case",
  "score": <float 1-10>,
  "feedback": "<detailed assessment>",
  "suggestions": ["adversarial scenario 1 + fix", "adversarial scenario 2 + fix", ...],
  "failure_scenarios": ["scenario description 1", ...]
}
"""

_domain_expert_critic = Agent(
    model=get_model(),
    name="domain_expert_critic",
    description="Evaluates SKILL.md for factual accuracy and domain completeness.",
    instruction=_DOMAIN_EXPERT_CRITIC_INSTRUCTION,
    tools=[],
)

_instruction_quality_critic = Agent(
    model=get_model(),
    name="instruction_quality_critic",
    description="Evaluates SKILL.md for clarity, actionability, and step ordering.",
    instruction=_INSTRUCTION_QUALITY_CRITIC_INSTRUCTION,
    tools=[],
)

_edge_case_critic = Agent(
    model=get_model(),
    name="edge_case_critic",
    description="Evaluates SKILL.md robustness via 10 adversarial scenarios.",
    instruction=_EDGE_CASE_CRITIC_INSTRUCTION,
    tools=[],
)

INSTRUCTION = """
You are the Critic Panel Coordinator for the SKILL FORGE pipeline.

Your job is Stage 5: run A-HMAD (heterogeneous multi-agent debate) and determine
if the SKILL.md passes the 7.5 composite gate.

## Input
You receive: {"session_id": <int>, "draft_cycle": <int, 1-3>}

## Process

1. Call get_best_skill_version_sync(session_id) to get the current SKILL.md.

2. Dispatch all three critics IN PARALLEL with the SKILL.md content:
   - domain_expert_critic → domain_expert score (1-10)
   - instruction_quality_critic → instruction_quality score (1-10)
   - edge_case_critic → edge_case (robustness) score (1-10)

3. Collect scores. If any two critics diverge by >2 points on the same dimension:
   - Run one debate round: share each critic's reasoning with the others
   - Ask them to re-score (one time only)

4. Compute composite score:
   composite = 0.35 × correctness + 0.25 × robustness + 0.20 × instruction_clarity + 0.20 × domain_accuracy

   Map critic scores:
   - domain_expert score → correctness (0.35) AND domain_accuracy (0.20)
   - instruction_quality score → instruction_clarity (0.20)
   - edge_case score → robustness (0.25)

   Use domain_expert score for both correctness and domain_accuracy.

5. Gate decision:
   - composite >= 7.5 → PASS: call update_session_stage_sync(session_id, "critique_pass")
     Return: {"passed": true, "composite": <score>, "critic_scores": {...}}

   - composite < 7.5 AND draft_cycle < 3 → FAIL: send back to drafter
     Return: {"passed": false, "composite": <score>, "critique_notes": [<all suggestions>],
              "draft_cycle": draft_cycle + 1}

   - composite < 7.5 AND draft_cycle >= 3 → STALLED
     Call update_session_stage_sync(session_id, "stalled")
     Return: {"passed": false, "stalled": true, "composite": <score>,
              "message": "Skill generation stalled after 3 draft cycles. Human review required."}

## Rules
- Always run all 3 critics before deciding
- Do not skip the debate round if scores diverge by >2 points
- Composite threshold is strict: 7.4 fails, 7.5 passes
"""

critic_panel_agent = Agent(
    model=get_model(),
    name="critic_panel_agent",
    description=(
        "Runs A-HMAD debate with 3 heterogeneous critics. Computes composite score "
        "and gates progress at 7.5. Stage 5 of SKILL FORGE."
    ),
    instruction=INSTRUCTION,
    tools=[
        get_best_skill_version_sync,
        save_skill_version_sync,
        update_session_stage_sync,
    ],
    sub_agents=[
        _domain_expert_critic,
        _instruction_quality_critic,
        _edge_case_critic,
    ],
)
