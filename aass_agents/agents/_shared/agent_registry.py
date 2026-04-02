"""
Agent Registry — maps every agent to its department and metadata.

Single source of truth for agent-to-department mapping, used by:
  - Cost tracker (aggregate costs by department)
  - Tool registry (filter tools by department)
  - Dashboard (agent status views)
"""
from typing import Optional


# Frozen mapping: agent_name -> department
AGENT_DEPARTMENT_MAP: dict[str, str] = {
    # ── Company Level ────────────────────────────────────────────────────────
    "company_orchestrator":           "company",
    # ── Sales ────────────────────────────────────────────────────────────────
    "sales_orchestrator":             "sales",
    "lead_researcher":                "sales",
    "outreach_composer":              "sales",
    "sales_call_prep":                "sales",
    "objection_handler":              "sales",
    "proposal_generator":             "sales",
    "crm_updater":                    "sales",
    "deal_analyst":                   "sales",
    # ── Marketing ────────────────────────────────────────────────────────────
    "marketing_orchestrator":         "marketing",
    "audience_builder":               "marketing",
    "campaign_composer":              "marketing",
    "content_strategist":             "marketing",
    "seo_analyst":                    "marketing",
    "campaign_analyst":               "marketing",
    "brand_voice":                    "marketing",
    # ── Product ──────────────────────────────────────────────────────────────
    "product_orchestrator":           "product",
    "pm_agent":                       "product",
    "architect_agent":                "product",
    "backend_builder_agent":          "product",
    "frontend_builder_agent":         "product",
    "db_agent":                       "product",
    "devops_agent":                   "product",
    "qa_agent":                       "product",
    # ── Engineering ──────────────────────────────────────────────────────────
    "engineering_orchestrator":        "engineering",
    "solutions_architect_agent":       "engineering",
    "data_engineer_agent":             "engineering",
    "ml_engineer_agent":               "engineering",
    "systems_engineer_agent":          "engineering",
    "integration_engineer_agent":      "engineering",
    "platform_engineer_agent":         "engineering",
    "sdet_agent":                      "engineering",
    # ── Research & Development ───────────────────────────────────────────────
    "research_orchestrator":           "research",
    "research_scientist_agent":        "research",
    "ml_researcher_agent":             "research",
    "applied_scientist_agent":         "research",
    "data_scientist_agent":            "research",
    "competitive_analyst_agent":       "research",
    "user_researcher_agent":           "research",
    "knowledge_manager_agent":         "research",
    # ── QA & Testing ─────────────────────────────────────────────────────────
    "qa_orchestrator":                 "qa",
    "test_architect_agent":            "qa",
    "test_automation_engineer_agent":  "qa",
    "performance_engineer_agent":      "qa",
    "security_tester_agent":           "qa",
    "qa_engineer_agent":               "qa",
    "chaos_engineer_agent":            "qa",
    # ── Autoresearcher ───────────────────────────────────────────────────────
    "autoresearcher_orchestrator":     "autoresearcher",
    "hypothesis_agent":                "autoresearcher",
    "evaluator_agent":                 "autoresearcher",
    "rewriter_agent":                  "autoresearcher",
    "rollback_watchdog_agent":         "autoresearcher",
    # ── Skill Forge ──────────────────────────────────────────────────────────
    "forge_orchestrator":              "forge",
    # ── Meta ─────────────────────────────────────────────────────────────────
    "reflection_agent":                "meta",
}

ALL_DEPARTMENTS: tuple[str, ...] = (
    "company", "sales", "marketing", "product", "engineering",
    "research", "qa", "autoresearcher", "forge", "meta",
)


def get_department(agent_name: str) -> str:
    """Return the department for an agent, or 'unknown'."""
    return AGENT_DEPARTMENT_MAP.get(agent_name, "unknown")


def get_agents_in_department(department: str) -> list[str]:
    """Return all agent names in a department."""
    return [
        name for name, dept in AGENT_DEPARTMENT_MAP.items()
        if dept == department
    ]
