"""
Smoke tests for critic_panel_agent.

Verifies agent loads with 3 critic sub-agents and instruction describes
the A-HMAD debate process. Never calls the live LLM.
"""


def test_critic_panel_agent_imports():
    from agents.skill_forge.critic_panel_agent import critic_panel_agent
    assert critic_panel_agent.name == "critic_panel_agent"


def test_critic_panel_has_three_sub_agents():
    from agents.skill_forge.critic_panel_agent import critic_panel_agent
    assert len(critic_panel_agent.sub_agents) == 3


def test_critic_panel_has_domain_expert_critic():
    from agents.skill_forge.critic_panel_agent import critic_panel_agent
    names = {a.name for a in critic_panel_agent.sub_agents}
    assert "domain_expert_critic" in names


def test_critic_panel_has_instruction_quality_critic():
    from agents.skill_forge.critic_panel_agent import critic_panel_agent
    names = {a.name for a in critic_panel_agent.sub_agents}
    assert "instruction_quality_critic" in names


def test_critic_panel_has_edge_case_critic():
    from agents.skill_forge.critic_panel_agent import critic_panel_agent
    names = {a.name for a in critic_panel_agent.sub_agents}
    assert "edge_case_critic" in names


def test_critic_panel_instruction_mentions_composite_gate():
    from agents.skill_forge.critic_panel_agent import INSTRUCTION
    assert "7.5" in INSTRUCTION


def test_critic_panel_instruction_mentions_a_hmad():
    from agents.skill_forge.critic_panel_agent import INSTRUCTION
    assert "A-HMAD" in INSTRUCTION or "debate" in INSTRUCTION.lower()


def test_critic_panel_instruction_mentions_parallel():
    from agents.skill_forge.critic_panel_agent import INSTRUCTION
    assert "parallel" in INSTRUCTION.lower()


def test_critic_panel_instruction_mentions_stalled():
    from agents.skill_forge.critic_panel_agent import INSTRUCTION
    assert "stalled" in INSTRUCTION.lower()


def test_critic_panel_instruction_mentions_max_cycles():
    from agents.skill_forge.critic_panel_agent import INSTRUCTION
    assert "draft_cycle" in INSTRUCTION


def test_critic_panel_has_get_best_version_tool():
    from agents.skill_forge.critic_panel_agent import critic_panel_agent
    from tools.skill_forge_db import get_best_skill_version_sync
    assert get_best_skill_version_sync in critic_panel_agent.tools


def test_domain_expert_critic_sub_agent():
    from agents.skill_forge.critic_panel_agent import _domain_expert_critic
    assert _domain_expert_critic.name == "domain_expert_critic"


def test_instruction_quality_critic_sub_agent():
    from agents.skill_forge.critic_panel_agent import _instruction_quality_critic
    assert _instruction_quality_critic.name == "instruction_quality_critic"


def test_edge_case_critic_sub_agent():
    from agents.skill_forge.critic_panel_agent import _edge_case_critic
    assert _edge_case_critic.name == "edge_case_critic"
