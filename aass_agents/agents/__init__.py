# Backward-compatible re-exports after department subdirectory reorganization.
# All agents remain importable by their original flat names:
#   from agents.sales_orchestrator_agent import sales_orchestrator  ✓

# Shared
from agents._shared.reflection_agent import reflection_agent

# Sales
from agents.sales.crm_updater_agent import crm_updater_agent
from agents.sales.deal_analyst_agent import deal_analyst_agent
from agents.sales.lead_researcher_agent import lead_researcher_agent
from agents.sales.objection_handler_agent import objection_handler_agent
from agents.sales.outreach_composer_agent import outreach_composer_agent
from agents.sales.proposal_generator_agent import proposal_generator_agent
from agents.sales.sales_call_prep_agent import sales_call_prep_agent
from agents.sales.sales_orchestrator_agent import sales_orchestrator

# Marketing
from agents.marketing.audience_builder_agent import audience_builder_agent
from agents.marketing.brand_voice_agent import brand_voice_agent
from agents.marketing.campaign_analyst_agent import campaign_analyst_agent
from agents.marketing.campaign_composer_agent import campaign_composer_agent
from agents.marketing.content_strategist_agent import content_strategist_agent
from agents.marketing.marketing_orchestrator_agent import marketing_orchestrator
from agents.marketing.seo_analyst_agent import seo_analyst_agent

# Product
from agents.product.architect_agent import architect_agent
from agents.product.backend_builder_agent import backend_builder_agent
from agents.product.db_agent import db_agent
from agents.product.devops_agent import devops_agent
from agents.product.frontend_builder_agent import frontend_builder_agent
from agents.product.pm_agent import pm_agent
from agents.product.product_orchestrator_agent import product_orchestrator
from agents.product.qa_agent import qa_agent

# Engineering
from agents.engineering.data_engineer_agent import data_engineer_agent
from agents.engineering.engineering_orchestrator_agent import engineering_orchestrator
from agents.engineering.integration_engineer_agent import integration_engineer_agent
from agents.engineering.ml_engineer_agent import ml_engineer_agent
from agents.engineering.platform_engineer_agent import platform_engineer_agent
from agents.engineering.sdet_agent import sdet_agent
from agents.engineering.solutions_architect_agent import solutions_architect_agent
from agents.engineering.systems_engineer_agent import systems_engineer_agent

# Research
from agents.research.applied_scientist_agent import applied_scientist_agent
from agents.research.competitive_analyst_agent import competitive_analyst_agent
from agents.research.data_scientist_agent import data_scientist_agent
from agents.research.knowledge_manager_agent import knowledge_manager_agent
from agents.research.ml_researcher_agent import ml_researcher_agent
from agents.research.research_orchestrator_agent import research_orchestrator
from agents.research.research_scientist_agent import research_scientist_agent
from agents.research.user_researcher_agent import user_researcher_agent

# QA
from agents.qa.chaos_engineer_agent import chaos_engineer_agent
from agents.qa.performance_engineer_agent import performance_engineer_agent
from agents.qa.qa_engineer_agent import qa_engineer_agent
from agents.qa.qa_orchestrator_agent import qa_orchestrator
from agents.qa.security_tester_agent import security_tester_agent
from agents.qa.test_architect_agent import test_architect_agent
from agents.qa.test_automation_engineer_agent import test_automation_engineer_agent

# Autoresearcher
from agents.autoresearcher.autoresearcher_orchestrator_agent import autoresearcher_orchestrator
from agents.autoresearcher.evaluator_agent import evaluator_agent
from agents.autoresearcher.hypothesis_agent import hypothesis_agent
from agents.autoresearcher.rewriter_agent import rewriter_agent
from agents.autoresearcher.rollback_watchdog_agent import rollback_watchdog_agent

__all__ = [
    # Shared
    "reflection_agent",
    # Sales
    "crm_updater_agent", "deal_analyst_agent", "lead_researcher_agent",
    "objection_handler_agent", "outreach_composer_agent", "proposal_generator_agent",
    "sales_call_prep_agent", "sales_orchestrator",
    # Marketing
    "audience_builder_agent", "brand_voice_agent", "campaign_analyst_agent",
    "campaign_composer_agent", "content_strategist_agent", "marketing_orchestrator",
    "seo_analyst_agent",
    # Product
    "architect_agent", "backend_builder_agent", "db_agent", "devops_agent",
    "frontend_builder_agent", "pm_agent", "product_orchestrator", "qa_agent",
    # Engineering
    "data_engineer_agent", "engineering_orchestrator", "integration_engineer_agent",
    "ml_engineer_agent", "platform_engineer_agent", "sdet_agent",
    "solutions_architect_agent", "systems_engineer_agent",
    # Research
    "applied_scientist_agent", "competitive_analyst_agent", "data_scientist_agent",
    "knowledge_manager_agent", "ml_researcher_agent", "research_orchestrator",
    "research_scientist_agent", "user_researcher_agent",
    # QA
    "chaos_engineer_agent", "performance_engineer_agent", "qa_engineer_agent",
    "qa_orchestrator", "security_tester_agent", "test_architect_agent",
    "test_automation_engineer_agent",
    # Autoresearcher
    "autoresearcher_orchestrator", "evaluator_agent", "hypothesis_agent",
    "rewriter_agent", "rollback_watchdog_agent",
]
