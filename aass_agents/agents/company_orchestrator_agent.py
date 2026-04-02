"""
Company Orchestrator — top-level agent coordinating all seven departments.

Departments: Sales, Marketing, Product, Engineering, Research & Development,
QA & Testing, Autoresearcher (self-evolving quality loop).
"""

import os
from google.adk.agents import Agent
from agents.sales.sales_orchestrator_agent import sales_orchestrator
from agents.marketing.marketing_orchestrator_agent import marketing_orchestrator
from agents.product.product_orchestrator_agent import product_orchestrator
from agents.engineering.engineering_orchestrator_agent import engineering_orchestrator
from agents.research.research_orchestrator_agent import research_orchestrator
from agents.qa.qa_orchestrator_agent import qa_orchestrator
from agents.autoresearcher.autoresearcher_orchestrator_agent import autoresearcher_orchestrator
from agents.skill_forge.forge_orchestrator_agent import forge_orchestrator
from tools.memory_tools import (
    save_deal_context, recall_deal_context,
    list_active_deals, save_agent_output, recall_past_outputs,
)
# build_and_run removed from company orchestrator — product_orchestrator handles builds

from agents._shared.model import get_model
from agents._shared.context_rules import STABLE_PREFIX, ERROR_PRESERVATION_RULE, TODO_PROTOCOL
from tools.todo_tools import write_todo, read_todo, complete_todo_step, get_todo_summary

INSTRUCTION = f"""{STABLE_PREFIX}

You route tasks to the right department via transfer_to_agent. ALWAYS use transfer_to_agent to delegate. NEVER call build_and_run or open_in_browser directly — let sub-agents handle tools.

## Routing
- prospect/outreach/deal/CRM/pipeline/objection → sales_orchestrator
- campaign/SEO/content/ad/brand/audience → marketing_orchestrator
- build/ship/create app/SaaS/product/website/UAT → product_orchestrator
- pipeline/ETL/ML/deploy/infra/integrate/toolchain → engineering_orchestrator
- research/SOTA/feasibility/competitor/A-B test/persona → research_orchestrator
- load test/security test/chaos/regression/perf test → qa_orchestrator
- "autoresearcher:"/improve agents/evolve/rollback → autoresearcher_orchestrator
- forge skill/create skill/staged skills → forge_orchestrator

## Disambiguation
UAT/acceptance test → product_orchestrator. Pipeline test → engineering_orchestrator. Perf/security/chaos test → qa_orchestrator.

## Auto-Triggers
- product shipped → show URL, then auto-route to marketing_orchestrator with product_name, one_liner, target_user, features, url
- MQL from marketing → auto-pass to sales_orchestrator
- Deal close: WIN → marketing (case study), LOSS → marketing (nurture)
- Research intel → sales (battle card) + marketing (messaging), must be reflection-checked
- QA PASS → notify team. QA CRITICAL → block release, route back.

## Memory
Session start: list_active_deals. After handoff: save_deal_context. Before task: recall_past_outputs.

{TODO_PROTOCOL}

{ERROR_PRESERVATION_RULE}
"""

company_orchestrator = Agent(
    model=get_model(),
    name="company_orchestrator",
    description=(
        "Top-level orchestrator coordinating all six departments: Sales, Marketing, Product, "
        "Engineering, Research & Development, and QA & Testing. Routes tasks to the right department, "
        "manages cross-department handoffs, and maintains shared company context."
    ),
    instruction=INSTRUCTION,
    sub_agents=[
        marketing_orchestrator,
        sales_orchestrator,
        product_orchestrator,
        engineering_orchestrator,
        research_orchestrator,
        qa_orchestrator,
        autoresearcher_orchestrator,
        forge_orchestrator,
    ],
    tools=[
        save_deal_context,
        recall_deal_context,
        list_active_deals,
        save_agent_output,
        recall_past_outputs,
        write_todo,
        read_todo,
        complete_todo_step,
        get_todo_summary,
    ],
)
