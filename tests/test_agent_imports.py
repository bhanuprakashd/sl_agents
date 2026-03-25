"""
Smoke tests — verify every agent module imports cleanly and exposes
the correct ADK Agent instance with expected name.
These tests NEVER call the live LLM.
"""
import pytest


# ── Engineering specialists ──────────────────────────────────────────────────

def test_solutions_architect_agent_imports():
    from agents.solutions_architect_agent import solutions_architect_agent
    assert solutions_architect_agent.name == "solutions_architect_agent"


def test_data_engineer_agent_imports():
    from agents.data_engineer_agent import data_engineer_agent
    assert data_engineer_agent.name == "data_engineer_agent"


def test_ml_engineer_agent_imports():
    from agents.ml_engineer_agent import ml_engineer_agent
    assert ml_engineer_agent.name == "ml_engineer_agent"


def test_systems_engineer_agent_imports():
    from agents.systems_engineer_agent import systems_engineer_agent
    assert systems_engineer_agent.name == "systems_engineer_agent"


def test_integration_engineer_agent_imports():
    from agents.integration_engineer_agent import integration_engineer_agent
    assert integration_engineer_agent.name == "integration_engineer_agent"


def test_platform_engineer_agent_imports():
    from agents.platform_engineer_agent import platform_engineer_agent
    assert platform_engineer_agent.name == "platform_engineer_agent"


def test_sdet_agent_imports():
    from agents.sdet_agent import sdet_agent
    assert sdet_agent.name == "sdet_agent"
