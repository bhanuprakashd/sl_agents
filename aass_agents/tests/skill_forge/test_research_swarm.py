"""
Smoke tests for research_swarm_agent.

Verifies agent definition loads, has correct sub-agents, and instruction
references parallel research coordination. Never calls the live LLM.
"""


def test_research_swarm_agent_imports():
    from agents.skill_forge.research_swarm_agent import research_swarm_agent
    assert research_swarm_agent.name == "research_swarm_agent"


def test_research_swarm_has_three_sub_agents():
    from agents.skill_forge.research_swarm_agent import research_swarm_agent
    assert len(research_swarm_agent.sub_agents) == 3


def test_research_swarm_has_domain_researcher():
    from agents.skill_forge.research_swarm_agent import research_swarm_agent
    names = {a.name for a in research_swarm_agent.sub_agents}
    assert "domain_researcher" in names


def test_research_swarm_has_benchmark_researcher():
    from agents.skill_forge.research_swarm_agent import research_swarm_agent
    names = {a.name for a in research_swarm_agent.sub_agents}
    assert "benchmark_researcher" in names


def test_research_swarm_has_technique_researcher():
    from agents.skill_forge.research_swarm_agent import research_swarm_agent
    names = {a.name for a in research_swarm_agent.sub_agents}
    assert "technique_researcher" in names


def test_research_swarm_instruction_mentions_parallel():
    from agents.skill_forge.research_swarm_agent import INSTRUCTION
    assert "parallel" in INSTRUCTION.lower()


def test_research_swarm_instruction_mentions_save_bundle():
    from agents.skill_forge.research_swarm_agent import INSTRUCTION
    assert "save_research_bundle_sync" in INSTRUCTION


def test_research_swarm_has_save_bundle_tool():
    from agents.skill_forge.research_swarm_agent import research_swarm_agent
    from tools.skill_forge_db import save_research_bundle_sync
    assert save_research_bundle_sync in research_swarm_agent.tools


def test_research_swarm_has_get_bundles_tool():
    from agents.skill_forge.research_swarm_agent import research_swarm_agent
    from tools.skill_forge_db import get_research_bundles_sync
    assert get_research_bundles_sync in research_swarm_agent.tools


def test_domain_researcher_sub_agent():
    from agents.skill_forge.research_swarm_agent import _domain_researcher
    assert _domain_researcher.name == "domain_researcher"


def test_benchmark_researcher_sub_agent():
    from agents.skill_forge.research_swarm_agent import _benchmark_researcher
    assert _benchmark_researcher.name == "benchmark_researcher"


def test_technique_researcher_sub_agent():
    from agents.skill_forge.research_swarm_agent import _technique_researcher
    assert _technique_researcher.name == "technique_researcher"
