# aass_agents/tools/neondb_tools.py
"""
NeonDB API tools for provisioning Postgres databases.
Requires: NEONDB_API_KEY env var
"""
import os
import httpx

_NEON_API = "https://console.neon.tech/api/v2"
_TIMEOUT = 60


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {os.environ['NEONDB_API_KEY']}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def create_project(name: str, region_id: str = "aws-us-east-2") -> dict:
    """
    Create a NeonDB project with a default branch + endpoint.
    Returns project info including connection_uri.
    """
    with httpx.Client(timeout=_TIMEOUT) as c:
        r = c.post(
            f"{_NEON_API}/projects",
            headers=_headers(),
            json={"project": {"name": name, "region_id": region_id}},
        )
        r.raise_for_status()
        return r.json()


def get_connection_uri(project_id: str, database_name: str = "neondb", role_name: str = "neondb_owner") -> str:
    """Return the postgres:// connection string for a project."""
    with httpx.Client(timeout=_TIMEOUT) as c:
        r = c.get(
            f"{_NEON_API}/projects/{project_id}/connection_uri",
            headers=_headers(),
            params={"database_name": database_name, "role_name": role_name},
        )
        r.raise_for_status()
        return r.json()["uri"]


def run_sql(project_id: str, branch_id: str, sql: str, database_name: str = "neondb") -> dict:
    """Execute SQL against a NeonDB branch using the SQL endpoint."""
    with httpx.Client(timeout=_TIMEOUT) as c:
        r = c.post(
            f"{_NEON_API}/projects/{project_id}/branches/{branch_id}/query",
            headers=_headers(),
            json={"query": sql, "database_name": database_name},
        )
        r.raise_for_status()
        return r.json()


def delete_project(project_id: str) -> None:
    """Delete a NeonDB project (used in cleanup)."""
    with httpx.Client(timeout=_TIMEOUT) as c:
        r = c.delete(f"{_NEON_API}/projects/{project_id}", headers=_headers())
        r.raise_for_status()
