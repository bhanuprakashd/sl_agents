"""
Sales Agent Team — Google ADK Entry Point

Run modes:
  python main.py              # Interactive CLI session
  python main.py --web        # Launch ADK web UI
  python main.py reset-circuit <agent_name>   # Reset a tripped circuit breaker
  python main.py resume <run_id>              # Resume a DLQ-blocked pipeline run
  adk api_server main.py      # Start as API server
"""

import os
import sys
import asyncio
import uuid
from dotenv import load_dotenv

load_dotenv()

from agents.company_orchestrator_agent import company_orchestrator
from tools.supervisor import Supervisor
from tools.supervisor_db import init_supervisor_tables

# Initialise supervisor tables before any agent runs
init_supervisor_tables()

_supervisor = Supervisor()


# ── ADK Callbacks ─────────────────────────────────────────────────────────────

def _before_agent_callback(callback_context):
    """
    Runs BEFORE ADK dispatches any agent call in the tree.
    Returns Content to skip the agent (guard triggered); None to allow.
    """
    from google.genai.types import Content, Part

    run_id = callback_context.state.get("supervisor_run_id")
    agent_name = getattr(callback_context, "agent_name", "unknown")
    user_content = getattr(callback_context, "user_content", None)
    input_text = ""
    if user_content and hasattr(user_content, "parts") and user_content.parts:
        input_text = user_content.parts[0].text or ""

    block_msg = _supervisor.pre_call_check(run_id, agent_name, input_text)
    if block_msg:
        return Content(parts=[Part(text=block_msg)])

    _supervisor.log_called(run_id, agent_name, input_text)
    return None


def _after_agent_callback(callback_context, agent_response):
    """
    Runs AFTER ADK gets the agent's response.
    Used for logging, checkpointing, and validity updates.
    """
    run_id = callback_context.state.get("supervisor_run_id")
    agent_name = getattr(callback_context, "agent_name", "unknown")
    output_text = ""
    if agent_response and hasattr(agent_response, "parts") and agent_response.parts:
        output_text = agent_response.parts[0].text or ""

    _supervisor.log_returned(run_id, agent_name, output_text)
    _supervisor.checkpoint(run_id, agent_name)
    _supervisor.update_validity(run_id, agent_name, dict(callback_context.state))
    return None  # pass response through unchanged


# Attach callbacks to root agent — ADK propagates to all sub-agents
company_orchestrator.before_agent_callback = _before_agent_callback
company_orchestrator.after_agent_callback = _after_agent_callback

# Export root_agent for ADK CLI and web UI discovery
root_agent = company_orchestrator


def _generate_orgchart():
    """Generate standalone HTML org chart from agent tree. No API calls required."""
    try:
        from tools.generate_orgchart import run as orgchart_run
        orgchart_run(out="orgchart.html", open_browser=False)
    except Exception as exc:
        print(f"[OrgChart] Generation skipped: {exc}")


# ── CLI Session ───────────────────────────────────────────────────────────────

async def run_cli():
    """Run an interactive CLI session with the GTM orchestrator."""
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai.types import Content, Part

    session_service = InMemorySessionService()
    APP_NAME = "sales-agent-team"
    USER_ID = "rep-001"
    SESSION_ID = "session-001"

    await session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID,
    )

    runner = Runner(
        agent=company_orchestrator,
        app_name=APP_NAME,
        session_service=session_service,
    )

    _generate_orgchart()

    from shared.memory_store import DB_PATH
    print("\n" + "═" * 60)
    print("  Sales Agent Team — Powered by Google ADK")
    print("═" * 60)
    print("  Sales:     Research · Outreach · Call Prep · Objections · Proposals · CRM")
    print("  Marketing: Audience · Campaigns · Content · SEO · Analytics · Brand Voice")
    print("  Product:   PRD · Architecture · Infra · DB · Backend · Frontend · QA")
    print(f"  Memory:    {DB_PATH}")
    print("═" * 60)
    print("  Type 'quit' to exit\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        if user_input.lower() in ("quit", "exit", "q"):
            print("Session ended.")
            break
        if not user_input:
            continue

        # Create a new supervised run for each top-level request
        run_id = str(uuid.uuid4())
        pipeline_type = "sales"  # orchestrator will adjust; coarse default
        _supervisor.pipeline_run.start(pipeline_type, {"input": user_input})

        content = Content(role="user", parts=[Part(text=user_input)])

        print("\nGTM Team: ", end="", flush=True)
        try:
            async for event in runner.run_async(
                user_id=USER_ID,
                session_id=SESSION_ID,
                new_message=content,
            ):
                # Inject run_id into session state for callbacks
                if hasattr(event, "actions") and event.actions:
                    for action in event.actions:
                        if hasattr(action, "state_delta"):
                            action.state_delta["supervisor_run_id"] = run_id

                if event.is_final_response():
                    if event.content and event.content.parts:
                        print(event.content.parts[0].text)
                elif hasattr(event, "author") and event.author not in (
                    "company_orchestrator", "sales_orchestrator",
                    "marketing_orchestrator", "product_orchestrator",
                ):
                    print(f"\n[{event.author}] ", end="", flush=True)

            _supervisor.pipeline_run.complete(run_id)
        except Exception as exc:
            _supervisor.pipeline_run.fail(run_id, str(exc))
            print(f"\n⚠ Run failed: {exc}")
        print()


# ── CLI Commands ──────────────────────────────────────────────────────────────

def cmd_reset_circuit(agent_name: str) -> None:
    from tools.supervisor import CircuitBreaker
    CircuitBreaker.reset(agent_name)
    print(f"✓ Circuit breaker reset for: {agent_name}")


def cmd_resume(run_id: str) -> None:
    row = _supervisor._db.get_run(run_id)
    if not row:
        print(f"✗ Run not found: {run_id}")
        return
    import json
    checkpoint = json.loads(row["checkpoint_json"] or "{}")
    print(f"Run {run_id} | Status: {row['status']} | Step: {row['current_step']}")
    print(f"Checkpoint: {checkpoint}")
    print("Start a new session and reference this run_id to resume from this point.")


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--web" in args:
        import subprocess
        subprocess.run(["adk", "web"], cwd=os.path.dirname(os.path.abspath(__file__)))
    elif args and args[0] == "reset-circuit":
        if len(args) < 2:
            print("Usage: python main.py reset-circuit <agent_name>")
        else:
            cmd_reset_circuit(args[1])
    elif args and args[0] == "resume":
        if len(args) < 2:
            print("Usage: python main.py resume <run_id>")
        else:
            cmd_resume(args[1])
    else:
        asyncio.run(run_cli())
