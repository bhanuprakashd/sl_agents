# aass_agents/agents/product/product_orchestrator_agent.py
"""
Product Orchestrator v5 — SequentialAgent pipeline with architect critic loop
and parallel build stage.

Pipeline: Setup → PM (rich PRD) → Architect Loop (architect ↔ critic, max 3) →
          Parallel Build (DB + Backend || then Frontend) →
          QA (smoke tests) → Ship (finalize + learn)

Uses ADK SequentialAgent for deterministic flow, LoopAgent for iterative
architecture refinement, and ParallelAgent for concurrent build stages.

The architect loop runs architect_agent → architect_critic_agent up to 3 times.
The critic calls approve_architecture() (escalate=True) to exit early when satisfied.

The build stage uses a two-phase approach:
  Phase 1 (parallel): db_agent + backend_builder_agent run concurrently
  Phase 2 (sequential): frontend_builder_agent runs after (needs backend_url)
"""
import os

from google.adk.agents import SequentialAgent, ParallelAgent, LoopAgent

from agents.product.setup_agent import setup_agent
from agents.product.pm_agent import pm_agent
from agents.product.architect_agent import architect_agent
from agents.product.architect_critic_agent import architect_critic_agent
from agents.product.db_agent import db_agent
from agents.product.backend_builder_agent import backend_builder_agent
from agents.product.frontend_builder_agent import frontend_builder_agent
from agents.product.qa_agent import qa_agent
from agents.product.ship_agent import ship_agent

# ── Phase 1: DB + Backend in parallel ────────────────────────────────────────
# These are independent — db_agent generates schema SQL, backend_builder
# generates FastAPI code and deploys. No data dependency between them.
parallel_build_phase = ParallelAgent(
    name="parallel_build_phase",
    description=(
        "Runs database schema generation and backend build concurrently. "
        "db_agent → state['db_output'], backend_builder → state['backend_output']."
    ),
    sub_agents=[
        db_agent,               # → state["db_output"]
        backend_builder_agent,  # → state["backend_output"]
    ],
)

# ── Composite builder: parallel phase → frontend (needs backend_url) ─────────
composite_builder = SequentialAgent(
    name="composite_builder",
    description=(
        "Two-phase build: first runs DB + backend in parallel, "
        "then frontend sequentially (needs backend_url from phase 1)."
    ),
    sub_agents=[
        parallel_build_phase,      # Phase 1: DB + backend concurrently
        frontend_builder_agent,    # Phase 2: frontend → state["frontend_output"]
    ],
)

# ── Architect refinement loop: architect → critic, max 3 iterations ───────────
# The critic calls approve_architecture() (sets escalate=True) to exit early.
# If max_iterations is reached, the last architecture_output is used as-is.
_max_arch_iterations = int(os.getenv("ARCHITECT_MAX_ITERATIONS", "3"))

architect_loop = LoopAgent(
    name="architect_loop",
    description=(
        "Iteratively refines architecture: architect generates, critic reviews. "
        "Exits when critic approves or after max iterations."
    ),
    sub_agents=[architect_agent, architect_critic_agent],
    max_iterations=_max_arch_iterations,
)

# ── Toggle: set ARCHITECT_LOOP=0 to skip critic and use single-pass architect ─
_use_arch_loop = os.getenv("ARCHITECT_LOOP", "1") != "0"
_architect_stage = architect_loop if _use_arch_loop else architect_agent

# ── Toggle: set PARALLEL_BUILD=0 to use original monolithic builder ──────────
_use_parallel = os.getenv("PARALLEL_BUILD", "1") != "0"

if _use_parallel:
    _builder = composite_builder
else:
    from agents.product.builder_agent import builder_agent
    _builder = builder_agent

product_orchestrator = SequentialAgent(
    name="product_orchestrator",
    description=(
        "Coordinates the full product pipeline using SequentialAgent: "
        "setup → PRD → architect loop (architect ↔ critic) → "
        "parallel build (DB+backend || frontend) → QA → ship. "
        "Each agent saves output to session state via output_key."
    ),
    sub_agents=[
        setup_agent,       # Step 1: Generate product_id, save initial state
        pm_agent,          # Step 2: Research + PRD → state["prd_output"]
        _architect_stage,  # Step 3: Architecture loop → state["architecture_output"]
        _builder,          # Step 4: Parallel build → state["db/backend/frontend_output"]
        qa_agent,          # Step 5: Smoke tests → state["qa_output"]
        ship_agent,        # Step 6: Finalize, learn, return JSON → state["ship_output"]
    ],
)
