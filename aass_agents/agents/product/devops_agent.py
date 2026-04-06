# aass_agents/agents/devops_agent.py
"""
DevOps Agent — creates GitHub repo, Vercel project, Railway project, injects env vars.
Runs TWICE in pipeline:
  - First pass (Step 3): create infra, save IDs
  - Second pass (Step 4.5): inject DATABASE_URL after db_agent completes
"""
import os
from google.adk.agents import Agent
from tools.product_memory_tools import save_product_state, recall_product_state, log_step
from tools.github_tools import create_repo
from tools.vercel_tools import vercel_create_project, vercel_add_env_var, connect_github, get_deployment_url
from tools.railway_tools import railway_create_project, railway_add_env_var, deploy_from_github

from agents._shared.model import get_model
from agents._shared.mcp_hub import mcp_hub
INSTRUCTION = """
CRITICAL OUTPUT RULE: Begin DIRECTLY with the deliverable. NEVER write out your reasoning, tool errors, or internal deliberation. NEVER ask the user for decisions. NEVER offer options menus. If tools fail, use internal knowledge, label it [Knowledge-Based], and deliver. Just produce the output.

You are a DevOps agent. You set up the infrastructure for the product pipeline.

## Your Process

### First Pass (action: "setup_infra")
1. Call `recall_product_state` to get product_name and architecture
3. Create GitHub repo: name = product_name.lower() + "-app", mono-repo structure
4. Create Vercel project linked to /frontend subdir of that repo
5. Create Railway project
6. Save to product state: repo_url, repo_full_name, vercel_project_id, railway_project_id
7. Call `log_step` with step="devops" and all URLs

### Second Pass (action: "inject_vercel_env") — runs after Step 4 (db_agent)
1. Call `recall_product_state` to get vercel_project_id, database_url
2. Call `vercel_add_env` with DATABASE_URL
3. Done — no issue checkout needed

### Third Pass (action: "inject_railway_env") — runs after Step 5 (backend_builder_agent)
1. Call `recall_product_state` to get railway_project_id, railway_service_id, database_url
   (railway_service_id is saved by backend_builder_agent after deploy_from_github)
2. Call `railway_add_env` with DATABASE_URL and service_id
3. Done — no issue checkout needed

## Important
- Repo name must be URL-safe (lowercase, hyphens only)
- Railway deploy is triggered by backend_builder_agent, not here
- Vercel deploy is triggered by frontend_builder_agent, not here
"""

_mcp_tools = mcp_hub.get_toolsets(["docs", "github", "duckduckgo", "docker", "compose", "ci", "aws_docs"])

devops_agent = Agent(
    model=get_model(),
    name="devops_agent",
    description="Creates GitHub repo, Vercel project, Railway project, and injects environment variables.",
    instruction=INSTRUCTION,
    tools=[
        save_product_state, recall_product_state, log_step,
        create_repo, vercel_create_project, vercel_add_env_var, connect_github,
        railway_create_project, railway_add_env_var,
        *_mcp_tools,],
)
