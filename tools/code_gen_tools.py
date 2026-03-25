# sales-adk-agents/tools/code_gen_tools.py
"""
Claude API wrapper for generating code artifacts.
Uses claude-sonnet-4-6 for main code, claude-haiku-4-5-20251001 for lightweight tasks.
Requires: ANTHROPIC_API_KEY env var
"""
import os
import anthropic

_CLIENT: anthropic.Anthropic | None = None


def _client() -> anthropic.Anthropic:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _CLIENT


def generate_code(
    prompt: str,
    model: str = "claude-sonnet-4-6",
    max_tokens: int = 8192,
    system: str = "You are an expert software engineer. Return only code, no explanations.",
) -> str:
    """Generate code using Claude. Returns the raw text response."""
    msg = _client().messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


def generate_fastapi_backend(prd: dict, stack: dict) -> str:
    """Generate a FastAPI backend from a PRD and stack spec."""
    prompt = f"""Generate a complete FastAPI backend application.

PRD:
{prd}

Stack:
{stack}

Requirements:
- main.py with FastAPI app
- All routes from PRD
- Pydantic models
- DATABASE_URL from environment
- CORS enabled for frontend URL
- Health check at GET /health
- Requirements: fastapi, uvicorn, sqlalchemy, psycopg2-binary, pydantic

Return a single Python file (main.py content only)."""
    return generate_code(prompt)


def generate_nextjs_frontend(prd: dict, backend_url: str) -> str:
    """Generate a Next.js frontend from a PRD."""
    prompt = f"""Generate a Next.js 14 App Router frontend application.

PRD:
{prd}

Backend API URL: {backend_url}

Requirements:
- TypeScript
- Tailwind CSS
- shadcn/ui components
- app/page.tsx as main entry
- NEXT_PUBLIC_API_URL from environment
- All features from PRD

Return only the content of app/page.tsx."""
    return generate_code(prompt, model="claude-sonnet-4-6")


def generate_db_schema(prd: dict) -> str:
    """Generate SQL schema from PRD."""
    prompt = f"""Generate a PostgreSQL schema for this product.

PRD:
{prd}

Requirements:
- CREATE TABLE statements only
- Include id (UUID), created_at, updated_at on all tables
- Add appropriate indexes
- No stored procedures

Return only valid SQL."""
    return generate_code(prompt, model="claude-haiku-4-5-20251001", max_tokens=2048)
