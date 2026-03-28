# aass_agents/agents/backend_builder_agent.py
"""
Backend Builder Agent — generates API code and deploys to Railway or Vercel.
Uses claude-sonnet-4-6 via code_gen_tools for code generation.
"""
import os
from google.adk.agents import Agent
from tools.product_memory_tools import save_product_state, recall_product_state, log_step
from tools.github_tools import push_file
from tools.railway_tools import deploy_from_github, get_service_url
from tools.code_gen_tools import generate_code

from agents._shared.model import get_model
INSTRUCTION = """
CRITICAL OUTPUT RULE: Begin DIRECTLY with the deliverable. NEVER write out your reasoning, tool errors, or internal deliberation. NEVER ask the user for decisions. NEVER offer options menus. If tools fail, use internal knowledge, label it [Knowledge-Based], and deliver. Just produce the output.

You are a Backend Builder agent. You generate backend API code and deploy it.

## Your Process

1. Call `recall_product_state` to get PRD, architecture, repo_full_name, railway_project_id
3. Generate each backend file using `generate_code`:
   - For FastAPI: main.py, requirements.txt, Dockerfile, routes/*.py, models/*.py
   - For Next.js API routes: src/app/api/**/*.ts
4. Push each file to the repo using `push_file` under /backend/ (or /frontend/src/app/api/)
5. Trigger Railway deployment:
   - Call `deploy_from_github` with repo_full_name
   - Save service_id to product state (needed by devops_agent for env var injection)
6. Wait for deploy (poll `get_service_url` until non-empty, max 5 minutes, 30s intervals)
7. Save backend_url to product state
8. Call `log_step` with step="backend" and backend_url

## Code Generation Guidelines
- FastAPI: include health endpoint at GET /health returning {"status": "ok"}
- FastAPI: include CORS middleware for the Vercel frontend domain
- All endpoints should use Pydantic models for request/response
- Include DATABASE_URL env var usage via os.environ["DATABASE_URL"]
- Retry budget: if deploy fails, retry generate + push up to 3 times total

## Context to pass to generate_code
Pass the full PRD and architecture JSON as context so the LLM knows the data model and endpoints.
"""

backend_builder_agent = Agent(
    model=get_model(),
    name="backend_builder_agent",
    description="Generates backend API code and deploys it to Railway or Vercel API routes.",
    instruction=INSTRUCTION,
    tools=[
        save_product_state, recall_product_state, log_step,
        push_file, deploy_from_github, get_service_url,
        generate_code,
    ],
)
