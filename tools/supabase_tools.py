# sales-adk-agents/tools/supabase_tools.py
"""
Supabase Management API tools for provisioning projects.
Requires: SUPABASE_ACCESS_TOKEN env var
"""
import os
import time
import httpx

_SUPA_API = "https://api.supabase.com/v1"
_TIMEOUT = 120  # project creation can be slow


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {os.environ['SUPABASE_ACCESS_TOKEN']}",
        "Content-Type": "application/json",
    }


def create_project(
    name: str,
    db_pass: str,
    organization_id: str,
    region: str = "us-east-1",
) -> dict:
    """
    Create a Supabase project.
    Returns project info. Project may take ~30s to become active.
    """
    with httpx.Client(timeout=_TIMEOUT) as c:
        r = c.post(
            f"{_SUPA_API}/projects",
            headers=_headers(),
            json={
                "name": name,
                "db_pass": db_pass,
                "organization_id": organization_id,
                "region": region,
                "plan": "free",
            },
        )
        r.raise_for_status()
        return r.json()


def get_project(project_ref: str) -> dict:
    """Return project details including status."""
    with httpx.Client(timeout=_TIMEOUT) as c:
        r = c.get(f"{_SUPA_API}/projects/{project_ref}", headers=_headers())
        r.raise_for_status()
        return r.json()


def wait_for_active(project_ref: str, max_wait: int = 120) -> dict:
    """Poll until project status is ACTIVE_HEALTHY. Returns final project info."""
    deadline = time.time() + max_wait
    while time.time() < deadline:
        info = get_project(project_ref)
        if info.get("status") == "ACTIVE_HEALTHY":
            return info
        time.sleep(5)
    raise TimeoutError(f"Supabase project {project_ref} not healthy after {max_wait}s")


def run_sql(project_ref: str, sql: str) -> dict:
    """Execute SQL against a Supabase project."""
    with httpx.Client(timeout=_TIMEOUT) as c:
        r = c.post(
            f"{_SUPA_API}/projects/{project_ref}/database/query",
            headers=_headers(),
            json={"query": sql},
        )
        r.raise_for_status()
        return r.json()


def get_connection_string(project_ref: str, db_pass: str) -> str:
    """Return a postgres:// connection string for the project."""
    return f"postgresql://postgres.{project_ref}:{db_pass}@aws-0-us-east-1.pooler.supabase.com:6543/postgres"
