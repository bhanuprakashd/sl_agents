# aass_agents/agents/product/product_orchestrator_agent.py
"""
Product Orchestrator v3 — SequentialAgent pipeline.

Pipeline: Setup → PM (rich PRD) → Architect (open-source stack) →
          Builder (scaffold → features → polish + feedback loop) →
          QA (smoke tests) → Ship (finalize + learn)

Uses ADK SequentialAgent for deterministic flow — each agent's output_key
saves to session state, and the next agent reads it automatically.
No more transfer_to_agent issues where sub-agent text ends the pipeline.
"""
from google.adk.agents import SequentialAgent

from agents.product.setup_agent import setup_agent
from agents.product.pm_agent import pm_agent
from agents.product.architect_agent import architect_agent
from agents.product.builder_agent import builder_agent
from agents.product.qa_agent import qa_agent
from agents.product.ship_agent import ship_agent


product_orchestrator = SequentialAgent(
    name="product_orchestrator",
    description=(
        "Coordinates the full product pipeline using SequentialAgent: "
        "setup → PRD → architecture → build → QA → ship. "
        "Each agent saves output to session state via output_key, "
        "and the next agent reads it. Produces production-quality localhost apps."
    ),
    sub_agents=[
        setup_agent,      # Step 1: Generate product_id, save initial state
        pm_agent,         # Step 2: Research + PRD → state["prd_output"]
        architect_agent,  # Step 3: Tech stack + file tree → state["architecture_output"]
        builder_agent,    # Step 4: Build with feedback loop → state["build_output"]
        qa_agent,         # Step 5: Smoke tests → state["qa_output"]
        ship_agent,       # Step 6: Finalize, learn, return JSON → state["ship_output"]
    ],
)
