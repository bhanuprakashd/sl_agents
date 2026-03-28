"""
Smoke tests for skill_drafter_agent.

Verifies agent definition loads correctly and instruction describes
the SKILL.md drafting pattern. Never calls the live LLM.
"""


def test_skill_drafter_agent_imports():
    from agents.skill_forge.skill_drafter_agent import skill_drafter_agent
    assert skill_drafter_agent.name == "skill_drafter_agent"


def test_skill_drafter_has_description():
    from agents.skill_forge.skill_drafter_agent import skill_drafter_agent
    assert skill_drafter_agent.description
    assert len(skill_drafter_agent.description) > 10


def test_skill_drafter_instruction_mentions_skill_md():
    from agents.skill_forge.skill_drafter_agent import INSTRUCTION
    assert "SKILL.md" in INSTRUCTION


def test_skill_drafter_instruction_mentions_dspy_gepa():
    from agents.skill_forge.skill_drafter_agent import INSTRUCTION
    assert "DSPy" in INSTRUCTION or "GEPA" in INSTRUCTION


def test_skill_drafter_instruction_mentions_draft_cycle():
    from agents.skill_forge.skill_drafter_agent import INSTRUCTION
    assert "draft_cycle" in INSTRUCTION


def test_skill_drafter_instruction_mentions_critique_notes():
    from agents.skill_forge.skill_drafter_agent import INSTRUCTION
    assert "critique_notes" in INSTRUCTION


def test_skill_drafter_has_save_version_tool():
    from agents.skill_forge.skill_drafter_agent import skill_drafter_agent
    from tools.skill_forge_db import save_skill_version_sync
    assert save_skill_version_sync in skill_drafter_agent.tools


def test_skill_drafter_has_get_versions_tool():
    from agents.skill_forge.skill_drafter_agent import skill_drafter_agent
    from tools.skill_forge_db import get_skill_versions_sync
    assert get_skill_versions_sync in skill_drafter_agent.tools


def test_skill_drafter_has_update_stage_tool():
    from agents.skill_forge.skill_drafter_agent import skill_drafter_agent
    from tools.skill_forge_db import update_session_stage_sync
    assert update_session_stage_sync in skill_drafter_agent.tools


def test_skill_drafter_has_no_sub_agents():
    from agents.skill_forge.skill_drafter_agent import skill_drafter_agent
    assert not skill_drafter_agent.sub_agents
