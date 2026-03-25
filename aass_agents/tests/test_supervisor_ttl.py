# tests/test_supervisor_ttl.py
"""Verify all new agents have TTL entries in AGENT_TTL_DAYS."""


def test_engineering_agents_have_ttl():
    from tools.supervisor_db import AGENT_TTL_DAYS
    for agent in [
        "engineering_orchestrator", "solutions_architect_agent", "data_engineer_agent",
        "ml_engineer_agent", "systems_engineer_agent", "integration_engineer_agent",
        "platform_engineer_agent", "sdet_agent",
    ]:
        assert agent in AGENT_TTL_DAYS, f"Missing TTL entry: {agent}"


def test_research_agents_have_ttl():
    from tools.supervisor_db import AGENT_TTL_DAYS
    for agent in [
        "research_orchestrator", "research_scientist_agent", "ml_researcher_agent",
        "applied_scientist_agent", "data_scientist_agent", "competitive_analyst_agent",
        "user_researcher_agent", "knowledge_manager_agent",
    ]:
        assert agent in AGENT_TTL_DAYS, f"Missing TTL entry: {agent}"


def test_qa_agents_have_ttl():
    from tools.supervisor_db import AGENT_TTL_DAYS
    for agent in [
        "qa_orchestrator", "test_architect_agent", "test_automation_engineer_agent",
        "performance_engineer_agent", "security_tester_agent", "qa_engineer_agent",
        "chaos_engineer_agent",
    ]:
        assert agent in AGENT_TTL_DAYS, f"Missing TTL entry: {agent}"


def test_key_ttl_values():
    from tools.supervisor_db import AGENT_TTL_DAYS
    assert AGENT_TTL_DAYS["engineering_orchestrator"] is None
    assert AGENT_TTL_DAYS["solutions_architect_agent"] == float("inf")
    assert AGENT_TTL_DAYS["research_scientist_agent"] == 30
    assert AGENT_TTL_DAYS["competitive_analyst_agent"] == 7
    assert AGENT_TTL_DAYS["test_architect_agent"] == float("inf")
    assert AGENT_TTL_DAYS["qa_orchestrator"] is None
    assert AGENT_TTL_DAYS["ml_researcher_agent"] == 14
    assert AGENT_TTL_DAYS["performance_engineer_agent"] == 7
