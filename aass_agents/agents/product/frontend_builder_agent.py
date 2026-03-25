# aass_agents/agents/frontend_builder_agent.py
"""
Frontend Builder Agent — generates Next.js UI and deploys to Vercel.
"""
import os
from google.adk.agents import Agent
from tools.product_memory_tools import save_product_state, recall_product_state, log_step
from tools.github_tools import push_file
from tools.vercel_tools import trigger_deploy, get_deployment_url
from tools.code_gen_tools import generate_code

MODEL = os.getenv("MODEL_ID", "gemini-2.0-flash")

INSTRUCTION = """
You are a Frontend Builder agent. You generate a Next.js UI and deploy it to Vercel.

## Your Process

1. Call `recall_product_state` to get PRD, architecture, repo_full_name, vercel_project_id, backend_url
3. Generate frontend files using `generate_code`:
   - package.json (Next.js 14, tailwindcss, shadcn/ui)
   - next.config.js
   - tailwind.config.js
   - src/app/layout.tsx
   - src/app/page.tsx (main landing/dashboard page)
   - src/app/globals.css
   - Key component files from architecture.file_tree
4. Push each file under /frontend/ using `push_file`
5. Trigger Vercel deployment: call `trigger_deploy` with vercel_project_id
6. Poll `get_deployment_url` until non-empty (max 5 minutes, 30s intervals)
7. Save frontend_url to product state
8. Call `log_step` with step="frontend" and frontend_url

## Code Generation Guidelines
- Use Next.js App Router (src/app/ structure)
- Use Tailwind CSS for all styling — no custom CSS files except globals.css
- Use shadcn/ui components (Button, Card, Input, etc.)
- NEXT_PUBLIC_API_URL env var should point to backend_url
- Include a basic loading state for async operations
- Keep it functional — no animations or polish for v1
- Retry budget: if build fails, regenerate and push up to 3 times total
"""

frontend_builder_agent = Agent(
    model=MODEL,
    name="frontend_builder_agent",
    description="Generates Next.js 14 + Tailwind UI and deploys it to Vercel.",
    instruction=INSTRUCTION,
    tools=[
        save_product_state, recall_product_state, log_step,
        push_file, trigger_deploy, get_deployment_url,
        generate_code,
    ],
)
