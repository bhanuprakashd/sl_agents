"""
Research Swarm Agent — Stage 2 of the SKILL FORGE pipeline.

Coordinates 3 parallel sub-agents (domain, benchmark, technique researchers)
that each produce a ResearchBundle with findings and citations.
"""
from google.adk.agents import Agent
from agents._shared.model import get_model
from agents._shared.mcp_hub import mcp_hub
from tools.skill_forge_db import (
    init_db,
    save_research_bundle_sync,
    get_research_bundles_sync,
    update_session_stage_sync,
)

init_db()

_DOMAIN_RESEARCHER_INSTRUCTION = """
CRITICAL OUTPUT RULE: Begin DIRECTLY with the deliverable. NEVER write out your reasoning, tool errors, or internal deliberation. NEVER ask the user for decisions. NEVER offer options menus. If tools fail, use internal knowledge, label it [Knowledge-Based], and deliver. Just produce the output.

You are the Domain Researcher in the SKILL FORGE research swarm.

Your role: extract deep domain expert knowledge for the skill being generated.

Research and compile:
- Expert mental models and decision heuristics used by top practitioners
- Common mistakes made by non-experts
- Best practices from authoritative sources (papers, expert blogs, practitioner guides)
- Case studies demonstrating excellence in this domain
- Tacit knowledge that separates 75th from 99th percentile performers

Output a ResearchBundle as JSON:
{
  "researcher_type": "domain",
  "findings": {
    "expert_mental_models": [...],
    "decision_heuristics": [...],
    "common_mistakes": [...],
    "best_practices": [...],
    "tacit_knowledge": [...]
  },
  "citations": ["source1", "source2", ...]
}

Be thorough. This knowledge forms the foundation of the skill's constitutional principles.
"""

_BENCHMARK_RESEARCHER_INSTRUCTION = """
You are the Benchmark Researcher in the SKILL FORGE research swarm.

Your role: find gold standard outputs and scoring rubrics for the skill being generated.

Research and compile:
- Gold standard output examples from top 1% practitioners
- Scoring rubrics used in competitions or professional audits
- Benchmark datasets if available
- Human baseline performance data
- Published quality criteria from domain authorities

Output a ResearchBundle as JSON:
{
  "researcher_type": "benchmark",
  "findings": {
    "gold_standard_examples": [...],
    "scoring_rubrics": [...],
    "benchmark_datasets": [...],
    "human_baselines": [...],
    "quality_criteria": [...]
  },
  "citations": ["source1", "source2", ...]
}

Focus on what excellence looks like, not just adequacy.
"""

_TECHNIQUE_RESEARCHER_INSTRUCTION = """
You are the Technique Researcher in the SKILL FORGE research swarm.

Your role: find the latest prompting techniques, tool integrations, and structured
reasoning schemas applicable to the skill being generated.

Research and compile:
- Relevant prompting techniques from recent papers (CoT, GEPA, DSPy, etc.)
- Tool integrations that enhance skill performance
- Structured reasoning schemas appropriate for this task type
- Existing SKILL.md patterns in the codebase that are transferable
- ADK features that could be leveraged

Output a ResearchBundle as JSON:
{
  "researcher_type": "technique",
  "findings": {
    "prompting_techniques": [...],
    "tool_integrations": [...],
    "reasoning_schemas": [...],
    "transferable_patterns": [...],
    "adk_features": [...]
  },
  "citations": ["source1", "source2", ...]
}

Prioritise techniques with empirical evidence of performance improvement.
"""

# MCP tools for researchers — free + github (if token present)
# Domain: web search + docs + fetch + github + knowledge graph for deep domain knowledge
_domain_tools = mcp_hub.get_toolsets(["duckduckgo", "docs", "fetch", "github", "knowledge_graph"])
# Benchmark: web search + fetch + github for gold standards and rubrics
_benchmark_tools = mcp_hub.get_toolsets(["duckduckgo", "fetch", "npm_search", "github"])
# Technique: docs + code analysis + thinking + github + knowledge graph for prompting techniques and patterns
_technique_tools = mcp_hub.get_toolsets(["docs", "code_analysis", "thinking", "fetch", "github", "knowledge_graph"])

_domain_researcher = Agent(
    model=get_model(),
    name="domain_researcher",
    description="Extracts expert domain knowledge, mental models, and best practices.",
    instruction=_DOMAIN_RESEARCHER_INSTRUCTION,
    tools=[*_domain_tools],
)

_benchmark_researcher = Agent(
    model=get_model(),
    name="benchmark_researcher",
    description="Finds gold standard outputs, scoring rubrics, and benchmark data.",
    instruction=_BENCHMARK_RESEARCHER_INSTRUCTION,
    tools=[*_benchmark_tools],
)

_technique_researcher = Agent(
    model=get_model(),
    name="technique_researcher",
    description="Identifies latest prompting techniques, tools, and reasoning schemas.",
    instruction=_TECHNIQUE_RESEARCHER_INSTRUCTION,
    tools=[*_technique_tools],
)

INSTRUCTION = """
You are the Research Swarm Coordinator for the SKILL FORGE pipeline.

Your job is Stage 2: coordinate 3 parallel researchers and persist their findings.

## Input
You receive: {"session_id": <int>, "task_spec": <dict>}

## Process

1. Brief all three researchers with the task_spec context.

2. Dispatch to all three sub-agents IN PARALLEL:
   - domain_researcher — expert knowledge, mental models, best practices
   - benchmark_researcher — gold standards, scoring rubrics, human baselines
   - technique_researcher — prompting techniques, tools, reasoning schemas

3. For each researcher's output:
   - Call save_research_bundle_sync(session_id, researcher_type, findings, citations)
   - Failure handling: if a researcher crashes, retry once; proceed with 2/3 minimum

4. After all bundles are saved:
   - Call update_session_stage_sync(session_id, "research")
   - Call get_research_bundles_sync(session_id) to verify bundles were saved
   - Return: {"session_id": <id>, "bundles_saved": <count>, "stage": "research"}

## Rules
- Always run all three researchers before advancing
- If only 2/3 researchers succeed after retry, log the failure and proceed
- Do not synthesise or interpret the research — that is for expert_synthesizer_agent
"""

research_swarm_agent = Agent(
    model=get_model(),
    name="research_swarm_agent",
    description=(
        "Coordinates 3 parallel domain, benchmark, and technique researchers. "
        "Stage 2 of the SKILL FORGE pipeline."
    ),
    instruction=INSTRUCTION,
    tools=[
        save_research_bundle_sync,
        get_research_bundles_sync,
        update_session_stage_sync,
    ],
    sub_agents=[
        _domain_researcher,
        _benchmark_researcher,
        _technique_researcher,
    ],
)
