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
from tools.vercel_tools import create_project as vercel_create, add_env_var as vercel_add_env, connect_github, get_deployment_url
from tools.railway_tools import create_project as railway_create, add_env_var as railway_add_env, deploy_from_github

MODEL = os.getenv("MODEL_ID", "gemini-2.0-flash")

INSTRUCTION = """
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

devops_agent = Agent(
    model=MODEL,
    name="devops_agent",
    description="Creates GitHub repo, Vercel project, Railway project, and injects environment variables.",
    instruction=INSTRUCTION,
    tools=[
        save_product_state, recall_product_state, log_step,
        create_repo, vercel_create, vercel_add_env, connect_github,
        railway_create, railway_add_env,
    ],
)
