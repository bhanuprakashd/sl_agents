# aass_agents/agents/architect_agent.py
"""
Architect Agent — picks tech stack from open-source options and generates file tree.
Uses ADK output_key to auto-save architecture to session state.
"""
import os
from google.adk.agents import Agent
from google.adk.tools import ToolContext
from tools.agent_reach_tools import search_github_repos, search_github_code, read_webpage
from tools.system_env_tools import get_environment_summary

from agents._shared.model import get_model, DEEP


def read_state(key: str, tool_context: ToolContext) -> str:
    """Read a value from session state. Use this to get data saved by previous agents (e.g. key='prd_output' for the PRD)."""
    value = tool_context.state.get(key)
    if value is None:
        return f"No value found in state for key '{key}'"
    return str(value)


INSTRUCTION = """
You are an architect agent. Design the tech stack and file structure based on the PRD.
First, call read_state(key="prd_output") to get the PRD from session state.
Your response will be automatically saved to session state via output_key.

100% open-source, localhost only. No Supabase/Vercel/Firebase/Auth0/AWS.

## Stack Table
full-stack SaaS: Next.js 14 + API routes + SQLite + Prisma
full-stack python: Jinja2+HTMX+Alpine / Flask|FastAPI + SQLite + SQLAlchemy
API-heavy backend: React(Vite) + Express|Fastify + PostgreSQL + Prisma
API-heavy python: React(Vite) + FastAPI + PostgreSQL + SQLAlchemy
data-heavy app: Next.js 14 + PostgreSQL + Prisma
data-heavy python: Dash|Streamlit + FastAPI + PostgreSQL + SQLAlchemy
simple landing: Astro+Tailwind + SQLite + better-sqlite3
static: Astro|Hugo, no backend
CLI: Node|Python + SQLite

PRD tech_preferences OVERRIDE the table. User choice always wins.
Default styling: Tailwind+Headless UI. Auth: bcryptjs+JWT httpOnly cookies. Icons: Lucide/Heroicons.

## Environment Constraints (CRITICAL)
You MUST call get_environment_summary() BEFORE selecting a stack. It tells you what is
installed on the user's machine. Follow these fallback rules strictly:

- Database: If PostgreSQL is NOT installed → use SQLite (+ better-sqlite3 for Node, or SQLAlchemy+aiosqlite for Python)
- Database: If MySQL is NOT installed → use SQLite
- Message Queue: If Redis is NOT installed → skip Celery/BullMQ entirely. Use built-in async (asyncio, setTimeout, or in-process job queue)
- Container: If Docker is NOT installed → all services must run natively, no docker-compose
- Runtime: ONLY propose runtimes that are installed. No Node → no Next.js/React/Express. No Python → no Flask/Django.
- Package Manager: Use whichever is installed (npm > yarn > pnpm)

ALWAYS prefer what is installed over what is "best practice". A working app with SQLite
beats a broken app that assumes PostgreSQL.

## Process
1. Call get_environment_summary() to see what is installed on this machine
2. Call read_state(key="prd_output") to get the PRD
3. Research (do ALL before designing):
   a. search_github_repos for similar projects — find 3-5 repos
   b. search_github_code for key patterns
   c. read_webpage on top 1-2 repos for architecture patterns
4. Select stack from table (respecting tech_preferences AND environment constraints)
5. Output the architecture as a single JSON object (no markdown, no code fences, just raw JSON)

## Architecture JSON Fields
{
  "stack": {"frontend": "", "backend": "", "database": "", "orm": "", "styling": "", "auth": "", "runtime": ""},
  "file_tree": [{"file": "", "purpose": ""}],
  "api_endpoints": [{"method": "", "path": "", "description": ""}],
  "database_schema": "CREATE TABLE SQL with indexes and seed data",
  "design_system": {"primary_color": "", "secondary_color": "", "accent_color": "", "background": "", "font": "", "border_radius": "", "shadows": ""},
  "research_findings": {"repos_analyzed": [{"url": "", "stars": 0, "relevance": ""}], "patterns_to_reuse": [], "build_from_scratch": []},
  "environment_constraints": {"skipped": [{"tech": "", "reason": "", "fallback": ""}], "available": []}
}

## Rules
- On tool failure: use knowledge, label [Knowledge-Based], deliver anyway.
- Output ONLY the JSON object. No explanation, no markdown, no code fences.
"""

architect_agent = Agent(
    model=get_model(DEEP),  # Architecture decisions need maximum reasoning
    name="architect_agent",
    description="Picks open-source tech stack and generates comprehensive project file tree from PRD. Respects user tech preferences.",
    instruction=INSTRUCTION,
    output_key="architecture_output",  # Auto-save response to state["architecture_output"]
    tools=[read_state, get_environment_summary, search_github_repos, search_github_code, read_webpage],
)
