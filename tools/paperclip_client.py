"""
Paperclip REST API client.

Agents use this to interact with the Paperclip orchestration server:
  - fetch issue details
  - atomically checkout a task
  - post progress comments
  - mark issues done / release them

Environment variables (injected by Paperclip during a heartbeat run):
  PAPERCLIP_API_URL  — base URL of the Paperclip server, e.g. http://localhost:3100
  PAPERCLIP_API_KEY  — short-lived run JWT *or* long-lived agent API key
"""

import os
import httpx

_DEFAULT_TIMEOUT = 30


def _client() -> httpx.Client:
    api_url = os.environ.get("PAPERCLIP_API_URL", "http://localhost:3100")
    api_key = os.environ.get("PAPERCLIP_API_KEY", "")
    return httpx.Client(
        base_url=api_url,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        timeout=_DEFAULT_TIMEOUT,
    )


def get_issue(issue_id: str) -> dict:
    """Return full issue record from Paperclip."""
    with _client() as c:
        r = c.get(f"/api/issues/{issue_id}")
        r.raise_for_status()
        return r.json()


def checkout_issue(issue_id: str, agent_id: str, run_id: str) -> dict:
    """
    Atomically claim the issue for this agent.
    Raises httpx.HTTPStatusError(409) if already owned — never retry a 409.
    """
    with _client() as c:
        r = c.post(
            f"/api/issues/{issue_id}/checkout",
            headers={"X-Paperclip-Run-Id": run_id},
            json={"agentId": agent_id, "expectedStatuses": ["todo", "backlog", "blocked"]},
        )
        r.raise_for_status()
        return r.json()


def release_issue(issue_id: str) -> None:
    """Release the checkout without completing (e.g. on error)."""
    with _client() as c:
        r = c.post(f"/api/issues/{issue_id}/release")
        r.raise_for_status()


def complete_issue(issue_id: str) -> dict:
    """Mark issue as done."""
    with _client() as c:
        r = c.patch(f"/api/issues/{issue_id}", json={"status": "done"})
        r.raise_for_status()
        return r.json()


def add_comment(issue_id: str, text: str) -> dict:
    """Post a plain-text comment on an issue (progress update or final output)."""
    with _client() as c:
        r = c.post(f"/api/issues/{issue_id}/comments", json={"body": text})
        r.raise_for_status()
        return r.json()


def get_current_agent() -> dict:
    """Return the agent record for the currently authenticated API key."""
    with _client() as c:
        r = c.get("/api/agents/me")
        r.raise_for_status()
        return r.json()
