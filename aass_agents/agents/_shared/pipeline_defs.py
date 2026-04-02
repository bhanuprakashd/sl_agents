"""
Pipeline Definitions — declarative DAG templates for parallel execution.

Each pipeline is a list of ParallelTask objects defining the execution graph.
Prompts use {variable} placeholders that get substituted from context at runtime.
"""
from typing import Optional

from tools.parallel_executor import ParallelTask


# ── Product Build Pipeline ───────────────────────────────────────────────────
# PM (sequential) → Architect (sequential) → [Backend, Frontend, DB] (parallel) → QA

PRODUCT_BUILD_PIPELINE: list[ParallelTask] = [
    ParallelTask(
        agent_name="pm_agent",
        prompt=(
            "Create a comprehensive PRD for the following requirement:\n\n"
            "{requirement}\n\n"
            "Include: features, data model, design guidelines, API specs, "
            "market research (GitHub repos, competitors, proven patterns)."
        ),
    ),
    ParallelTask(
        agent_name="architect_agent",
        prompt=(
            "Design the architecture for this product based on the PRD below.\n\n"
            "PRD:\n{pm_agent}\n\n"
            "Search GitHub for similar repos and proven patterns. Output: "
            "tech stack, file tree, DB schema, design system, API specs, "
            "research_findings with repos analyzed."
        ),
        depends_on=("pm_agent",),
    ),
    ParallelTask(
        agent_name="backend_builder_agent",
        prompt=(
            "Build the backend based on this architecture:\n\n"
            "{architect_agent}\n\n"
            "Implement all API endpoints, database operations, authentication, "
            "and business logic. Follow the tech stack and patterns specified."
        ),
        depends_on=("architect_agent",),
    ),
    ParallelTask(
        agent_name="frontend_builder_agent",
        prompt=(
            "Build the frontend based on this architecture:\n\n"
            "{architect_agent}\n\n"
            "Implement all pages, components, routing, state management, "
            "and design system. Follow the tech stack and design guidelines."
        ),
        depends_on=("architect_agent",),
    ),
    ParallelTask(
        agent_name="db_agent",
        prompt=(
            "Set up the database based on this architecture:\n\n"
            "{architect_agent}\n\n"
            "Create schema, migrations, seed data, and indexes. "
            "Optimize for the query patterns described in the API specs."
        ),
        depends_on=("architect_agent",),
    ),
    ParallelTask(
        agent_name="qa_agent",
        prompt=(
            "Run QA on the completed build:\n\n"
            "Backend: {backend_builder_agent}\n\n"
            "Frontend: {frontend_builder_agent}\n\n"
            "Database: {db_agent}\n\n"
            "Test all critical paths, API endpoints, and UI flows. "
            "Report issues with severity and reproduction steps."
        ),
        depends_on=("backend_builder_agent", "frontend_builder_agent", "db_agent"),
    ),
]


# ── Research Pipeline ────────────────────────────────────────────────────────
# [Competitive Analysis, User Research, Market Research] (all parallel) → Knowledge Manager

RESEARCH_PIPELINE: list[ParallelTask] = [
    ParallelTask(
        agent_name="competitive_analyst_agent",
        prompt=(
            "Conduct competitive analysis for:\n\n{topic}\n\n"
            "Identify key competitors, their strengths/weaknesses, "
            "market positioning, and differentiators."
        ),
    ),
    ParallelTask(
        agent_name="user_researcher_agent",
        prompt=(
            "Conduct user research for:\n\n{topic}\n\n"
            "Identify target users, pain points, needs, "
            "and behavioral patterns."
        ),
    ),
    ParallelTask(
        agent_name="data_scientist_agent",
        prompt=(
            "Analyze available data for:\n\n{topic}\n\n"
            "Provide quantitative insights, trends, "
            "and data-driven recommendations."
        ),
    ),
    ParallelTask(
        agent_name="knowledge_manager_agent",
        prompt=(
            "Synthesize research findings into a comprehensive brief:\n\n"
            "Competitive Analysis:\n{competitive_analyst_agent}\n\n"
            "User Research:\n{user_researcher_agent}\n\n"
            "Data Analysis:\n{data_scientist_agent}\n\n"
            "Create an actionable research summary with key insights and recommendations."
        ),
        depends_on=(
            "competitive_analyst_agent",
            "user_researcher_agent",
            "data_scientist_agent",
        ),
    ),
]


# ── QA Pipeline ──────────────────────────────────────────────────────────────
# [Test Automation, Performance, Security] (all parallel) → Test Architect summary

QA_PIPELINE: list[ParallelTask] = [
    ParallelTask(
        agent_name="test_automation_engineer_agent",
        prompt=(
            "Create and run automated tests for:\n\n{target}\n\n"
            "Cover unit tests, integration tests, and API tests."
        ),
    ),
    ParallelTask(
        agent_name="performance_engineer_agent",
        prompt=(
            "Run performance testing for:\n\n{target}\n\n"
            "Test load capacity, response times, and resource usage."
        ),
    ),
    ParallelTask(
        agent_name="security_tester_agent",
        prompt=(
            "Run security testing for:\n\n{target}\n\n"
            "Check OWASP Top 10, auth bypass, injection, XSS, CSRF."
        ),
    ),
    ParallelTask(
        agent_name="test_architect_agent",
        prompt=(
            "Review all test results and provide QA assessment:\n\n"
            "Automated Tests:\n{test_automation_engineer_agent}\n\n"
            "Performance:\n{performance_engineer_agent}\n\n"
            "Security:\n{security_tester_agent}\n\n"
            "Provide go/no-go recommendation with risk assessment."
        ),
        depends_on=(
            "test_automation_engineer_agent",
            "performance_engineer_agent",
            "security_tester_agent",
        ),
    ),
]


# ── Sales Pipeline ───────────────────────────────────────────────────────────
# Lead Research → [Outreach + Call Prep] (parallel) → Proposal

SALES_PIPELINE: list[ParallelTask] = [
    ParallelTask(
        agent_name="lead_researcher",
        prompt=(
            "Research this lead/company thoroughly:\n\n{lead}\n\n"
            "Include company overview, decision makers, tech stack, "
            "recent news, and pain points."
        ),
    ),
    ParallelTask(
        agent_name="outreach_composer",
        prompt=(
            "Compose personalized outreach based on research:\n\n"
            "{lead_researcher}\n\n"
            "Create email sequence and talking points."
        ),
        depends_on=("lead_researcher",),
    ),
    ParallelTask(
        agent_name="sales_call_prep",
        prompt=(
            "Prepare for sales call based on research:\n\n"
            "{lead_researcher}\n\n"
            "Create call agenda, key questions, objection handling prep."
        ),
        depends_on=("lead_researcher",),
    ),
    ParallelTask(
        agent_name="proposal_generator",
        prompt=(
            "Generate proposal based on:\n\n"
            "Research: {lead_researcher}\n"
            "Outreach: {outreach_composer}\n"
            "Call Prep: {sales_call_prep}\n\n"
            "Create a comprehensive, personalized proposal."
        ),
        depends_on=("outreach_composer", "sales_call_prep"),
    ),
]


# ── Pipeline Registry ────────────────────────────────────────────────────────

PIPELINES: dict[str, list[ParallelTask]] = {
    "product_build": PRODUCT_BUILD_PIPELINE,
    "research": RESEARCH_PIPELINE,
    "qa": QA_PIPELINE,
    "sales": SALES_PIPELINE,
}


def get_pipeline(name: str) -> Optional[list[ParallelTask]]:
    """Retrieve a pipeline definition by name."""
    return PIPELINES.get(name)
