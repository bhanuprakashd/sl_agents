# sales-adk-agents/tools/github_tools.py
"""
GitHub API tools for creating repos and pushing files.
Requires: GITHUB_TOKEN env var (personal access token with repo scope)
"""
import base64
import os
import httpx

_GH_API = "https://api.github.com"
_TIMEOUT = 30


def _headers() -> dict:
    token = os.environ["GITHUB_TOKEN"]
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def create_repo(name: str, description: str = "", private: bool = False) -> dict:
    """Create a new GitHub repo. Returns repo info including clone_url and html_url."""
    with httpx.Client(timeout=_TIMEOUT) as c:
        r = c.post(
            f"{_GH_API}/user/repos",
            headers=_headers(),
            json={"name": name, "description": description, "private": private, "auto_init": True},
        )
        r.raise_for_status()
        return r.json()


def push_file(repo_full_name: str, path: str, content: str, message: str, branch: str = "main") -> dict:
    """
    Create or update a file in the repo.
    repo_full_name: "owner/repo"
    content: raw string (will be base64-encoded)
    """
    encoded = base64.b64encode(content.encode()).decode()
    url = f"{_GH_API}/repos/{repo_full_name}/contents/{path}"
    with httpx.Client(timeout=_TIMEOUT) as c:
        existing = c.get(url, headers=_headers())
        payload: dict = {"message": message, "content": encoded, "branch": branch}
        if existing.status_code == 200:
            payload["sha"] = existing.json()["sha"]
        r = c.put(url, headers=_headers(), json=payload)
        r.raise_for_status()
        return r.json()


def get_repo(repo_full_name: str) -> dict:
    """Return repo info."""
    with httpx.Client(timeout=_TIMEOUT) as c:
        r = c.get(f"{_GH_API}/repos/{repo_full_name}", headers=_headers())
        r.raise_for_status()
        return r.json()
