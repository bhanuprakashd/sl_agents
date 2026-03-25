# aass_agents/agents/architect_agent.py
"""
Architect Agent — picks tech stack deterministically and generates file tree.
Does NOT use DeerFlow — stack selection is rule-based to avoid non-determinism.
"""
import os
from google.adk.agents import Agent
from tools.product_memory_tools import save_product_state, recall_product_state, log_step

MODEL = os.getenv("MODEL_ID", "gemini-2.0-flash")

INSTRUCTION = """
You are a Software Architect agent. Your job is to pick the tech stack and generate
a complete file tree for the product.

## Stack Decision Table (USE EXACTLY — no deviation)

| product_type           | Frontend              | Backend                      | Database  |
|------------------------|-----------------------|------------------------------|-----------|
| full-stack SaaS        | Vercel (Next.js 14)  | Next.js API routes           | Supabase  |
| API-heavy backend      | Vercel (Next.js 14)  | Railway (FastAPI)            | NeonDB    |
| simple landing + auth  | Vercel (Next.js 14)  | Supabase Edge Functions      | Supabase  |
| data-heavy app         | Vercel (Next.js 14)  | Railway (FastAPI)            | NeonDB    |

## Selection Criteria
- full-stack SaaS: user-facing UI with CRUD operations
- API-heavy backend: primarily an API/webhook/data processing service, minimal UI
- simple landing + auth: marketing site or waitlist with basic signup
- data-heavy app: analytics, dashboards, large dataset queries

## Your Process

1. Call `recall_product_state` to get the PRD
3. Read `product_type` from PRD and select stack from table above
4. Generate architecture as JSON:
   - stack: {frontend, backend, database}
   - file_tree: flat list of all files to generate with their purpose
     - frontend files: all under /frontend/
     - backend files: all under /backend/
   - api_endpoints: list of endpoints the backend will expose
5. Call `save_product_state` with the architecture JSON
6. Call `log_step` with step="architect" and the stack summary

## File Tree Requirements
- /frontend/: package.json, next.config.js, tailwind.config.js, src/app/layout.tsx,
  src/app/page.tsx, src/app/globals.css, src/components/ (key UI components)
- /backend/: (FastAPI) main.py, requirements.txt, Dockerfile, routes/, models/
- /backend/: (Next.js API) included in /frontend/src/app/api/
"""

architect_agent = Agent(
    model=MODEL,
    name="architect_agent",
    description="Picks tech stack deterministically and generates project file tree from PRD.",
    instruction=INSTRUCTION,
    tools=[save_product_state, recall_product_state, log_step],
)
