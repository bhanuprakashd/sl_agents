"""
Smoke tests — verify every agent module imports cleanly and exposes
the correct ADK Agent instance with expected name.
These tests NEVER call the live LLM.
"""
import pytest


# ── Engineering specialists ──────────────────────────────────────────────────

def test_solutions_architect_agent_imports():
    from agents.engineering.solutions_architect_agent import solutions_architect_agent
    assert solutions_architect_agent.name == "solutions_architect_agent"


def test_data_engineer_agent_imports():
    from agents.engineering.data_engineer_agent import data_engineer_agent
    assert data_engineer_agent.name == "data_engineer_agent"


def test_ml_engineer_agent_imports():
    from agents.engineering.ml_engineer_agent import ml_engineer_agent
    assert ml_engineer_agent.name == "ml_engineer_agent"


def test_systems_engineer_agent_imports():
    from agents.engineering.systems_engineer_agent import systems_engineer_agent
    assert systems_engineer_agent.name == "systems_engineer_agent"


def test_integration_engineer_agent_imports():
    from agents.engineering.integration_engineer_agent import integration_engineer_agent
    assert integration_engineer_agent.name == "integration_engineer_agent"


def test_platform_engineer_agent_imports():
    from agents.engineering.platform_engineer_agent import platform_engineer_agent
    assert platform_engineer_agent.name == "platform_engineer_agent"


def test_sdet_agent_imports():
    from agents.engineering.sdet_agent import sdet_agent
    assert sdet_agent.name == "sdet_agent"


# ── Engineering orchestrator ──────────────────────────────────────────────────

def test_engineering_orchestrator_imports():
    from agents.engineering.engineering_orchestrator_agent import engineering_orchestrator
    assert engineering_orchestrator.name == "engineering_orchestrator"
    # 7 specialists + 1 reflection_agent = 8
    assert len(engineering_orchestrator.sub_agents) == 8


# ── Research specialists ──────────────────────────────────────────────────────

def test_research_scientist_agent_imports():
    from agents.research.research_scientist_agent import research_scientist_agent
    assert research_scientist_agent.name == "research_scientist_agent"

def test_ml_researcher_agent_imports():
    from agents.research.ml_researcher_agent import ml_researcher_agent
    assert ml_researcher_agent.name == "ml_researcher_agent"

def test_applied_scientist_agent_imports():
    from agents.research.applied_scientist_agent import applied_scientist_agent
    assert applied_scientist_agent.name == "applied_scientist_agent"

def test_data_scientist_agent_imports():
    from agents.research.data_scientist_agent import data_scientist_agent
    assert data_scientist_agent.name == "data_scientist_agent"

def test_competitive_analyst_agent_imports():
    from agents.research.competitive_analyst_agent import competitive_analyst_agent
    assert competitive_analyst_agent.name == "competitive_analyst_agent"

def test_user_researcher_agent_imports():
    from agents.research.user_researcher_agent import user_researcher_agent
    assert user_researcher_agent.name == "user_researcher_agent"

def test_knowledge_manager_agent_imports():
    from agents.research.knowledge_manager_agent import knowledge_manager_agent
    assert knowledge_manager_agent.name == "knowledge_manager_agent"


# ── Research orchestrator ─────────────────────────────────────────────────────

def test_research_orchestrator_imports():
    from agents.research.research_orchestrator_agent import research_orchestrator
    assert research_orchestrator.name == "research_orchestrator"
    # 7 specialists + 1 reflection_agent = 8
    assert len(research_orchestrator.sub_agents) == 8


# ── QA specialists ────────────────────────────────────────────────────────────

def test_test_architect_agent_imports():
    from agents.qa.test_architect_agent import test_architect_agent
    assert test_architect_agent.name == "test_architect_agent"

def test_test_automation_engineer_agent_imports():
    from agents.qa.test_automation_engineer_agent import test_automation_engineer_agent
    assert test_automation_engineer_agent.name == "test_automation_engineer_agent"

def test_performance_engineer_agent_imports():
    from agents.qa.performance_engineer_agent import performance_engineer_agent
    assert performance_engineer_agent.name == "performance_engineer_agent"

def test_security_tester_agent_imports():
    from agents.qa.security_tester_agent import security_tester_agent
    assert security_tester_agent.name == "security_tester_agent"

def test_qa_engineer_agent_imports():
    from agents.qa.qa_engineer_agent import qa_engineer_agent
    assert qa_engineer_agent.name == "qa_engineer_agent"

def test_chaos_engineer_agent_imports():
    from agents.qa.chaos_engineer_agent import chaos_engineer_agent
    assert chaos_engineer_agent.name == "chaos_engineer_agent"


# ── QA orchestrator ───────────────────────────────────────────────────────────

def test_qa_orchestrator_imports():
    from agents.qa.qa_orchestrator_agent import qa_orchestrator
    assert qa_orchestrator.name == "qa_orchestrator"
    # 6 specialists + 1 reflection_agent = 7
    assert len(qa_orchestrator.sub_agents) == 7


# ── Company orchestrator (updated) ───────────────────────────────────────────

def test_company_orchestrator_has_all_seven_departments():
    from agents.company_orchestrator_agent import company_orchestrator
    assert company_orchestrator.name == "company_orchestrator"
    sub_agent_names = {a.name for a in company_orchestrator.sub_agents}
    assert "sales_orchestrator" in sub_agent_names
    assert "marketing_orchestrator" in sub_agent_names
    assert "product_orchestrator" in sub_agent_names
    assert "engineering_orchestrator" in sub_agent_names
    assert "research_orchestrator" in sub_agent_names
    assert "qa_orchestrator" in sub_agent_names
    assert "autoresearcher_orchestrator" in sub_agent_names
    assert len(company_orchestrator.sub_agents) == 7
