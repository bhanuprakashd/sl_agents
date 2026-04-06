"""
Cross-Agent Learning — pattern transfer between related agents (ASI-Evolve).

When one agent's evolution succeeds (status → stable), this module extracts
transferable patterns and suggests them to sibling agents in the same department
or with similar roles across departments.
"""
import json
import asyncio
from typing import Optional

from tools import evolution_db
from tools.cognition_base_tools import search_cognition, add_cognition

# Department membership map — which agents belong to which department
DEPARTMENT_MAP = {
    "sales": [
        "lead_researcher_agent", "outreach_composer_agent", "sales_call_prep_agent",
        "objection_handler_agent", "proposal_generator_agent", "crm_updater_agent",
        "deal_analyst_agent",
    ],
    "marketing": [
        "audience_builder_agent", "campaign_composer_agent", "content_strategist_agent",
        "seo_analyst_agent", "campaign_analyst_agent", "brand_voice_agent",
    ],
    "product": [
        "pm_agent", "architect_agent", "backend_builder_agent",
        "frontend_builder_agent", "qa_agent", "db_agent", "devops_agent",
        "builder_agent", "setup_agent", "ship_agent",
    ],
    "engineering": [
        "data_engineer_agent", "ml_engineer_agent", "platform_engineer_agent",
        "solutions_architect_agent", "systems_engineer_agent",
        "integration_engineer_agent", "sdet_agent",
    ],
    "research": [
        "research_scientist_agent", "data_scientist_agent", "ml_researcher_agent",
        "competitive_analyst_agent", "user_researcher_agent",
        "applied_scientist_agent", "knowledge_manager_agent",
    ],
    "qa": [
        "qa_engineer_agent", "test_architect_agent", "test_automation_engineer_agent",
        "performance_engineer_agent", "security_tester_agent", "chaos_engineer_agent",
    ],
}

# Role-based groupings across departments (agents with similar meta-roles)
ROLE_GROUPS = {
    "orchestrator": [
        "company_orchestrator_agent", "product_orchestrator_agent",
        "engineering_orchestrator_agent", "marketing_orchestrator_agent",
        "sales_orchestrator_agent", "research_orchestrator_agent",
        "qa_orchestrator_agent",
    ],
    "analyst": [
        "deal_analyst_agent", "campaign_analyst_agent", "competitive_analyst_agent",
        "seo_analyst_agent", "data_scientist_agent",
    ],
    "builder": [
        "backend_builder_agent", "frontend_builder_agent", "builder_agent",
        "data_engineer_agent", "ml_engineer_agent",
    ],
    "researcher": [
        "lead_researcher_agent", "research_scientist_agent", "user_researcher_agent",
        "applied_scientist_agent", "ml_researcher_agent",
    ],
}


def _get_department(agent_name: str) -> Optional[str]:
    """Find which department an agent belongs to."""
    for dept, agents in DEPARTMENT_MAP.items():
        if agent_name in agents:
            return dept
    return None


def _get_role_group(agent_name: str) -> Optional[str]:
    """Find which role group an agent belongs to."""
    for role, agents in ROLE_GROUPS.items():
        if agent_name in agents:
            return role
    return None


def _get_sibling_agents(agent_name: str) -> list[str]:
    """Get related agents: same department + same role group across departments."""
    siblings = set()

    dept = _get_department(agent_name)
    if dept:
        for a in DEPARTMENT_MAP[dept]:
            if a != agent_name:
                siblings.add(a)

    role = _get_role_group(agent_name)
    if role:
        for a in ROLE_GROUPS[role]:
            if a != agent_name:
                siblings.add(a)

    return sorted(siblings)


def extract_transfer_patterns_sync(
    agent_name: str,
    hypothesis_text: str,
    root_cause: str,
) -> str:
    """Extract transferable patterns from a successful evolution and queue for siblings.

    Called after a rewrite is marked stable. Saves the pattern to the cognition base
    and creates low-priority queue entries for sibling agents.

    Args:
        agent_name: The agent whose evolution succeeded.
        hypothesis_text: The successful instruction improvement.
        root_cause: The diagnosed root cause that was fixed.

    Returns:
        JSON summary of transfer actions taken.
    """
    dept = _get_department(agent_name) or "general"
    siblings = _get_sibling_agents(agent_name)

    # Save the successful pattern to cognition base
    pattern_title = f"Successful evolution pattern from {agent_name}"
    pattern_content = (
        f"Root cause fixed: {root_cause}\n\n"
        f"Instruction improvement that worked:\n{hypothesis_text[:2000]}"
    )
    add_cognition(pattern_title, pattern_content, dept, source="cross_transfer")

    # Queue transfer hypotheses for sibling agents at low priority
    transfers_queued = []
    evidence = [{
        "source": "cross_transfer",
        "from_agent": agent_name,
        "root_cause": root_cause[:500],
        "pattern": hypothesis_text[:1000],
    }]

    for sibling in siblings[:5]:  # limit to 5 siblings to avoid noise
        try:
            evolution_db.enqueue_agent_sync(
                agent_name=sibling,
                priority=8.0,  # low priority (higher number = lower priority)
                evidence=evidence,
            )
            transfers_queued.append(sibling)
        except Exception:
            pass  # skip if already queued with higher priority

    return json.dumps({
        "source_agent": agent_name,
        "department": dept,
        "siblings_found": len(siblings),
        "transfers_queued": transfers_queued,
        "cognition_entry_saved": True,
    })


async def extract_transfer_patterns(
    agent_name: str,
    hypothesis_text: str,
    root_cause: str,
) -> str:
    return await asyncio.to_thread(
        extract_transfer_patterns_sync, agent_name, hypothesis_text, root_cause,
    )


def get_transfer_suggestions_sync(agent_name: str) -> str:
    """Get cognition-base suggestions relevant to an agent's department.

    Useful for hypothesis_agent to check if sibling agents have solved similar problems.

    Args:
        agent_name: The agent to get suggestions for.

    Returns:
        JSON with relevant cognition entries from the agent's department.
    """
    dept = _get_department(agent_name) or "general"
    results = search_cognition(
        query=f"instruction improvement patterns for {dept} agents",
        domain=dept,
        top_k=5,
    )
    return results


async def get_transfer_suggestions(agent_name: str) -> str:
    return await asyncio.to_thread(get_transfer_suggestions_sync, agent_name)
