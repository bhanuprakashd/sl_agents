"""
E2E smoke tests for forge_orchestrator_agent.

Verifies the orchestrator loads with all 8 sub-agents and correct tools.
Also verifies company_orchestrator includes forge_orchestrator.
Never calls the live LLM.
"""


def test_forge_orchestrator_imports():
    from agents.skill_forge.forge_orchestrator_agent import forge_orchestrator
    assert forge_orchestrator.name == "forge_orchestrator"


def test_forge_orchestrator_has_eight_sub_agents():
    from agents.skill_forge.forge_orchestrator_agent import forge_orchestrator
    assert len(forge_orchestrator.sub_agents) == 8


def test_forge_orchestrator_has_intent_parser():
    from agents.skill_forge.forge_orchestrator_agent import forge_orchestrator
    names = {a.name for a in forge_orchestrator.sub_agents}
    assert "intent_parser_agent" in names


def test_forge_orchestrator_has_research_swarm():
    from agents.skill_forge.forge_orchestrator_agent import forge_orchestrator
    names = {a.name for a in forge_orchestrator.sub_agents}
    assert "research_swarm_agent" in names


def test_forge_orchestrator_has_expert_synthesizer():
    from agents.skill_forge.forge_orchestrator_agent import forge_orchestrator
    names = {a.name for a in forge_orchestrator.sub_agents}
    assert "expert_synthesizer_agent" in names


def test_forge_orchestrator_has_skill_drafter():
    from agents.skill_forge.forge_orchestrator_agent import forge_orchestrator
    names = {a.name for a in forge_orchestrator.sub_agents}
    assert "skill_drafter_agent" in names


def test_forge_orchestrator_has_critic_panel():
    from agents.skill_forge.forge_orchestrator_agent import forge_orchestrator
    names = {a.name for a in forge_orchestrator.sub_agents}
    assert "critic_panel_agent" in names


def test_forge_orchestrator_has_red_team():
    from agents.skill_forge.forge_orchestrator_agent import forge_orchestrator
    names = {a.name for a in forge_orchestrator.sub_agents}
    assert "red_team_agent" in names


def test_forge_orchestrator_has_iteration_agent():
    from agents.skill_forge.forge_orchestrator_agent import forge_orchestrator
    names = {a.name for a in forge_orchestrator.sub_agents}
    assert "iteration_agent" in names


def test_forge_orchestrator_has_promoter():
    from agents.skill_forge.forge_orchestrator_agent import forge_orchestrator
    names = {a.name for a in forge_orchestrator.sub_agents}
    assert "promoter_agent" in names


def test_forge_orchestrator_instruction_mentions_all_stages():
    from agents.skill_forge.forge_orchestrator_agent import INSTRUCTION
    for stage_agent in [
        "intent_parser_agent",
        "research_swarm_agent",
        "expert_synthesizer_agent",
        "skill_drafter_agent",
        "critic_panel_agent",
        "red_team_agent",
        "iteration_agent",
        "promoter_agent",
    ]:
        assert stage_agent in INSTRUCTION, f"Stage {stage_agent!r} not found in orchestrator instruction"


def test_forge_orchestrator_instruction_mentions_trigger_phrases():
    from agents.skill_forge.forge_orchestrator_agent import INSTRUCTION
    assert "forge skill" in INSTRUCTION.lower()
    assert "generate skill for" in INSTRUCTION.lower()


def test_forge_orchestrator_instruction_mentions_resume():
    from agents.skill_forge.forge_orchestrator_agent import INSTRUCTION
    assert "resume" in INSTRUCTION.lower()


def test_forge_orchestrator_has_get_session_tool():
    from agents.skill_forge.forge_orchestrator_agent import forge_orchestrator
    from tools.skill_forge_db import get_session_sync
    assert get_session_sync in forge_orchestrator.tools


def test_forge_orchestrator_has_list_staged_skills_tool():
    from agents.skill_forge.forge_orchestrator_agent import forge_orchestrator
    from tools.skill_forge_db import list_staged_skills_sync
    assert list_staged_skills_sync in forge_orchestrator.tools


# ── company_orchestrator integration ──────────────────────────────────────────

def test_company_orchestrator_includes_forge_orchestrator():
    from agents.company_orchestrator_agent import company_orchestrator
    names = {a.name for a in company_orchestrator.sub_agents}
    assert "forge_orchestrator" in names


def test_company_orchestrator_routing_mentions_forge():
    from agents.company_orchestrator_agent import INSTRUCTION
    assert "forge_orchestrator" in INSTRUCTION
    assert "forge skill" in INSTRUCTION.lower()


def test_company_orchestrator_still_has_all_departments():
    from agents.company_orchestrator_agent import company_orchestrator
    names = {a.name for a in company_orchestrator.sub_agents}
    for expected in (
        "sales_orchestrator",
        "marketing_orchestrator",
        "product_orchestrator",
        "engineering_orchestrator",
        "research_orchestrator",
        "qa_orchestrator",
        "autoresearcher_orchestrator",
        "forge_orchestrator",
    ):
        assert expected in names, f"Missing: {expected}"
