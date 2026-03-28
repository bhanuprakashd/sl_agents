"""
Smoke tests for intent_parser_agent.

Verifies agent definition loads, has correct name, and instruction contains
key routing phrases. Never calls the live LLM.
"""


def test_intent_parser_agent_imports():
    from agents.skill_forge.intent_parser_agent import intent_parser_agent
    assert intent_parser_agent.name == "intent_parser_agent"


def test_intent_parser_agent_has_description():
    from agents.skill_forge.intent_parser_agent import intent_parser_agent
    assert intent_parser_agent.description
    assert len(intent_parser_agent.description) > 10


def test_intent_parser_instruction_contains_forge_phrase():
    from agents.skill_forge.intent_parser_agent import INSTRUCTION
    assert "forge skill" in INSTRUCTION.lower()


def test_intent_parser_instruction_contains_generate_phrase():
    from agents.skill_forge.intent_parser_agent import INSTRUCTION
    assert "generate skill for" in INSTRUCTION.lower()


def test_intent_parser_instruction_contains_task_spec():
    from agents.skill_forge.intent_parser_agent import INSTRUCTION
    assert "TaskSpec" in INSTRUCTION or "task_spec" in INSTRUCTION


def test_intent_parser_instruction_contains_session_creation():
    from agents.skill_forge.intent_parser_agent import INSTRUCTION
    assert "create_session_sync" in INSTRUCTION


def test_intent_parser_has_create_session_tool():
    from agents.skill_forge.intent_parser_agent import intent_parser_agent
    from tools.skill_forge_db import create_session_sync
    tool_funcs = [t for t in intent_parser_agent.tools]
    assert create_session_sync in tool_funcs


def test_intent_parser_has_get_session_tool():
    from agents.skill_forge.intent_parser_agent import intent_parser_agent
    from tools.skill_forge_db import get_session_sync
    assert get_session_sync in intent_parser_agent.tools


def test_intent_parser_has_no_sub_agents():
    from agents.skill_forge.intent_parser_agent import intent_parser_agent
    assert not intent_parser_agent.sub_agents
