# sales-adk-agents/tools/vercel_tools.py
"""
Vercel API tools for creating projects and deploying.
Requires: VERCEL_TOKEN env var
"""
import os
import httpx

_VERCEL_API = "https://api.vercel.com"
_TIMEOUT = 60


def _headers() -> dict:
    return {"Authorization": f"Bearer {os.environ['VERCEL_TOKEN']}"}


def create_project(name: str, framework: str = "nextjs", root_directory: str = "frontend") -> dict:
    """Create a Vercel project. Returns project id and name."""
    with httpx.Client(timeout=_TIMEOUT) as c:
        r = c.post(
            f"{_VERCEL_API}/v9/projects",
            headers=_headers(),
            json={"name": name, "framework": framework, "rootDirectory": root_directory},
        )
        r.raise_for_status()
        return r.json()


def add_env_var(project_id: str, key: str, value: str, target: list[str] | None = None) -> dict:
    """Add an environment variable to a Vercel project."""
    with httpx.Client(timeout=_TIMEOUT) as c:
        r = c.post(
            f"{_VERCEL_API}/v9/projects/{project_id}/env",
            headers=_headers(),
            json={
                "key": key,
                "value": value,
                "type": "encrypted",
                "target": target or ["production", "preview", "development"],
            },
        )
        r.raise_for_status()
        return r.json()


def connect_github(project_id: str, repo_full_name: str) -> dict:
    """Link a GitHub repo to the Vercel project."""
    owner, repo = repo_full_name.split("/", 1)
    with httpx.Client(timeout=_TIMEOUT) as c:
        r = c.patch(
            f"{_VERCEL_API}/v9/projects/{project_id}",
            headers=_headers(),
            json={"link": {"type": "github", "org": owner, "repo": repo}},
        )
        r.raise_for_status()
        return r.json()


def trigger_deploy(project_id: str) -> dict:
    """Trigger a new deployment and return deployment info including url."""
    with httpx.Client(timeout=_TIMEOUT) as c:
        r = c.post(
            f"{_VERCEL_API}/v13/deployments",
            headers=_headers(),
            json={"name": project_id, "gitSource": {"type": "github", "ref": "main"}},
        )
        r.raise_for_status()
        return r.json()


def get_deployment_url(project_id: str) -> str:
    """Return the latest production deployment URL."""
    with httpx.Client(timeout=_TIMEOUT) as c:
        r = c.get(
            f"{_VERCEL_API}/v6/deployments",
            headers=_headers(),
            params={"projectId": project_id, "limit": 1, "state": "READY"},
        )
        r.raise_for_status()
        deployments = r.json().get("deployments", [])
        if not deployments:
            return ""
        return f"https://{deployments[0]['url']}"
