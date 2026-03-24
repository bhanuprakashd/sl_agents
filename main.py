"""
Sales Agent Team — Google ADK Entry Point

Run modes:
  python main.py              # Interactive CLI session
  python main.py --web        # Launch ADK web UI
  adk api_server main.py      # Start as API server
"""

import os
import sys
import asyncio
from dotenv import load_dotenv

load_dotenv()

from agents.company_orchestrator_agent import company_orchestrator

# Export root_agent for ADK CLI and web UI discovery
root_agent = company_orchestrator


async def run_cli():
    """Run an interactive CLI session with the sales orchestrator."""
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai.types import Content, Part

    session_service = InMemorySessionService()
    APP_NAME = "sales-agent-team"
    USER_ID = "rep-001"
    SESSION_ID = "session-001"

    await session_service.create_session(
        app_name=APP_NAME,
        user_id=USER_ID,
        session_id=SESSION_ID,
    )

    runner = Runner(
        agent=company_orchestrator,
        app_name=APP_NAME,
        session_service=session_service,
    )

    from shared.memory_store import DB_PATH
    print("\n" + "═" * 60)
    print("  Sales Agent Team — Powered by Google ADK")
    print("═" * 60)
    print("  Sales:     Research · Outreach · Call Prep · Objections · Proposals · CRM · Pipeline")
    print("  Marketing: Audience · Campaigns · Content · SEO · Analytics · Brand Voice")
    print(f"  Memory:  {DB_PATH}")
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

        content = Content(role="user", parts=[Part(text=user_input)])

        print("\nGTM Team: ", end="", flush=True)
        async for event in runner.run_async(
            user_id=USER_ID,
            session_id=SESSION_ID,
            new_message=content,
        ):
            if event.is_final_response():
                if event.content and event.content.parts:
                    print(event.content.parts[0].text)
            elif hasattr(event, "author") and event.author not in (
                "company_orchestrator", "sales_orchestrator", "marketing_orchestrator"
            ):
                # Show which specialist agent is working
                print(f"\n[{event.author}] ", end="", flush=True)
        print()


if __name__ == "__main__":
    if "--web" in sys.argv:
        # Launch ADK web dev UI — discovers root_agent from this module
        import subprocess
        subprocess.run(["adk", "web"], cwd=os.path.dirname(os.path.abspath(__file__)))
    else:
        asyncio.run(run_cli())
