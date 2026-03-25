# sales-adk-agents/agents/db_agent.py
"""
DB Agent — generates SQL schema and provisions NeonDB or Supabase.
"""
import os
from google.adk.agents import Agent
from tools.product_memory_tools import save_product_state, recall_product_state, log_step
from tools.neondb_tools import create_project as neon_create, get_connection_uri as neon_conn, run_sql as neon_sql
from tools.supabase_tools import create_project as supa_create, get_connection_string as supa_conn, run_sql as supa_sql

MODEL = os.getenv("MODEL_ID", "gemini-2.0-flash")

INSTRUCTION = """
You are a Database agent. You provision the database and run the schema migration.

## Your Process

1. Call `recall_product_state` to get PRD (data_model) and architecture (database choice)
3. Generate SQL CREATE TABLE statements from data_model in PRD
4. Provision the database:
   - If architecture.stack.database == "Supabase": call `supa_create`
   - If architecture.stack.database == "NeonDB": call `neon_create`
   - On failure: try the other provider (fallback)
5. Run the SQL migration
6. Save `database_url` to product state via `save_product_state`
   (devops_agent will read this to inject DATABASE_URL env var)
7. Call `log_step` with step="db" and "Database provisioned: [provider] — migration complete"

## SQL Guidelines
- Always include: id (UUID or SERIAL PRIMARY KEY), created_at TIMESTAMP DEFAULT NOW()
- Use TEXT for strings, not VARCHAR
- Add basic indexes on foreign keys
- Keep it simple — no stored procedures, no triggers for v1
"""

db_agent = Agent(
    model=MODEL,
    name="db_agent",
    description="Generates SQL schema and provisions NeonDB or Supabase database.",
    instruction=INSTRUCTION,
    tools=[
        save_product_state, recall_product_state, log_step,
        neon_create, neon_conn, neon_sql,
        supa_create, supa_conn, supa_sql,
    ],
)
