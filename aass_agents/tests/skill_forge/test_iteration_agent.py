"""
Smoke tests for iteration_agent.

Verifies agent definition loads and instruction describes the GEPA loop.
Never calls the live LLM.
"""


def test_iteration_agent_imports():
    from agents.skill_forge.iteration_agent import iteration_agent
    assert iteration_agent.name == "iteration_agent"


def test_iteration_agent_has_description():
    from agents.skill_forge.iteration_agent import iteration_agent
    assert "GEPA" in iteration_agent.description


def test_iteration_instruction_mentions_gepa():
    from agents.skill_forge.iteration_agent import INSTRUCTION
    assert "GEPA" in INSTRUCTION


def test_iteration_instruction_mentions_max_iterations():
    from agents.skill_forge.iteration_agent import INSTRUCTION
    assert "10" in INSTRUCTION
    assert "iterations" in INSTRUCTION.lower()


def test_iteration_instruction_mentions_composite_gate():
    from agents.skill_forge.iteration_agent import INSTRUCTION
    assert "8.5" in INSTRUCTION


def test_iteration_instruction_mentions_rollback():
    from agents.skill_forge.iteration_agent import INSTRUCTION
    assert "rollback" in INSTRUCTION.lower()


def test_iteration_instruction_mentions_regression():
    from agents.skill_forge.iteration_agent import INSTRUCTION
    assert "regress" in INSTRUCTION.lower()


def test_iteration_instruction_mentions_reflect():
    from agents.skill_forge.iteration_agent import INSTRUCTION
    assert "reflect" in INSTRUCTION.lower()


def test_iteration_has_get_best_version_tool():
    from agents.skill_forge.iteration_agent import iteration_agent
    from tools.skill_forge_db import get_best_skill_version_sync
    assert get_best_skill_version_sync in iteration_agent.tools


def test_iteration_has_get_battle_test_tool():
    from agents.skill_forge.iteration_agent import iteration_agent
    from tools.skill_forge_db import get_battle_test_sync
    assert get_battle_test_sync in iteration_agent.tools


def test_iteration_has_save_version_tool():
    from agents.skill_forge.iteration_agent import iteration_agent
    from tools.skill_forge_db import save_skill_version_sync
    assert save_skill_version_sync in iteration_agent.tools


def test_iteration_has_save_battle_test_tool():
    from agents.skill_forge.iteration_agent import iteration_agent
    from tools.skill_forge_db import save_battle_test_sync
    assert save_battle_test_sync in iteration_agent.tools


def test_iteration_has_no_sub_agents():
    from agents.skill_forge.iteration_agent import iteration_agent
    assert not iteration_agent.sub_agents
