"""
Smoke tests for expert_synthesizer_agent.

Verifies agent definition loads correctly and instruction contains
key synthesis guidance. Never calls the live LLM.
"""


def test_expert_synthesizer_agent_imports():
    from agents.skill_forge.expert_synthesizer_agent import expert_synthesizer_agent
    assert expert_synthesizer_agent.name == "expert_synthesizer_agent"


def test_expert_synthesizer_has_description():
    from agents.skill_forge.expert_synthesizer_agent import expert_synthesizer_agent
    assert expert_synthesizer_agent.description
    assert "ExpertBlueprint" in expert_synthesizer_agent.description


def test_expert_synthesizer_instruction_mentions_constitutional():
    from agents.skill_forge.expert_synthesizer_agent import INSTRUCTION
    assert "constitutional" in INSTRUCTION.lower()


def test_expert_synthesizer_instruction_mentions_gold_examples():
    from agents.skill_forge.expert_synthesizer_agent import INSTRUCTION
    assert "gold_examples" in INSTRUCTION or "gold examples" in INSTRUCTION.lower()


def test_expert_synthesizer_instruction_mentions_failure_modes():
    from agents.skill_forge.expert_synthesizer_agent import INSTRUCTION
    assert "failure_mode" in INSTRUCTION.lower() or "failure mode" in INSTRUCTION.lower()


def test_expert_synthesizer_has_get_bundles_tool():
    from agents.skill_forge.expert_synthesizer_agent import expert_synthesizer_agent
    from tools.skill_forge_db import get_research_bundles_sync
    assert get_research_bundles_sync in expert_synthesizer_agent.tools


def test_expert_synthesizer_has_update_stage_tool():
    from agents.skill_forge.expert_synthesizer_agent import expert_synthesizer_agent
    from tools.skill_forge_db import update_session_stage_sync
    assert update_session_stage_sync in expert_synthesizer_agent.tools


def test_expert_synthesizer_has_no_sub_agents():
    from agents.skill_forge.expert_synthesizer_agent import expert_synthesizer_agent
    assert not expert_synthesizer_agent.sub_agents
