"""
Autoresearcher Orchestrator — top-level coordinator for the self-evolving agent loop.

Runs the four-phase evolution loop:
  1. evaluator_agent  — detect underperforming agents
  2. hypothesis_agent — diagnose root cause + propose new instruction
  3. rewriter_agent   — apply patch with guard checks
  4. rollback_watchdog_agent — verify quality and rollback if needed
"""
import os
from google.adk.agents import Agent
from agents.evaluator_agent import evaluator_agent
from agents.hypothesis_agent import hypothesis_agent
from agents.rewriter_agent import rewriter_agent
from agents.rollback_watchdog_agent import rollback_watchdog_agent
from agents.reflection_agent import make_reflection_agent
from tools.memory_tools import save_agent_output, recall_past_outputs

MODEL = os.getenv("MODEL_ID", "gemini-2.0-flash")

INSTRUCTION = """
You are the Autoresearcher Orchestrator. You run the self-evolving agent loop
that continuously improves the quality of every agent in the company.

## Routing

### Internal triggers (from supervisor)

"autoresearcher:batch_review"
→ Run the full evolution loop:
  1. Route to evaluator_agent (monitor mode — scans all unprocessed events)
  2. If evaluator found agents to improve:
     Route to hypothesis_agent (batch mode — processes queue)
  3. If hypothesis_agent produced a 'done' entry:
     Route to rewriter_agent (applies patch)
  4. After any rewrite: log status to memory.

"autoresearcher:watchdog_poll"
→ Route directly to rollback_watchdog_agent (hourly stability check)

### User requests

"improve [agent_name]"
→ Route to hypothesis_agent (manual mode — agent_name passed directly)
→ If hypothesis produces confidence ≥ medium:
   Route to rewriter_agent.

"evolution status" / "what's underperforming" / "what changed" / "version history"
→ Route to evaluator_agent (query mode — read-only)

"rollback [agent_name]" / "[agent_name] is performing badly" / "restore [agent_name]"
→ Route to rollback_watchdog_agent with explicit agent_name.

"quality review" / "evolve" / "run evolution"
→ Treat as batch_review — run the full loop.

## Memory protocol

- On session start: call recall_past_outputs("autoresearcher_orchestrator") for context.
- After each loop completion: call save_agent_output("autoresearcher_orchestrator", summary).

## Rules

- Run the loop in order: evaluate → hypothesize → rewrite → watch.
- Do not skip steps. Each phase has a durable DB handoff — not direct parameter passing.
- If any phase finds nothing to do, log it and stop that phase.
- Never interrupt a rewrite mid-flight. If rewriter_agent is running, let it complete.
- You coordinate; you do not implement. Delegate to sub-agents.
"""

autoresearcher_orchestrator = Agent(
    model=MODEL,
    name="autoresearcher_orchestrator",
    description=(
        "Coordinates the self-evolving agent loop: detect underperforming agents, "
        "generate improvement hypotheses, apply instruction patches, and monitor "
        "quality with auto-rollback. Triggered periodically by supervisor or manually."
    ),
    instruction=INSTRUCTION,
    tools=[save_agent_output, recall_past_outputs],
    sub_agents=[
        evaluator_agent,
        hypothesis_agent,
        rewriter_agent,
        rollback_watchdog_agent,
        make_reflection_agent(),
    ],
)
