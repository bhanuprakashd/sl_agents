"""
Paperclip HTTP Adapter Webhook Server

Bridges Paperclip's HTTP adapter to the Google ADK agent team.

How it works:
  1. Paperclip POSTs a heartbeat to POST /webhook
  2. We fetch the assigned issue from Paperclip API
  3. We checkout (claim) the issue atomically
  4. We run the ADK company_orchestrator with the issue as the prompt
  5. We post the agent's response as a comment and mark the issue done

Run:
  uvicorn paperclip_webhook:app --port 8080

Then configure Paperclip's HTTP adapter to point at:
  http://localhost:8080/webhook
"""

import asyncio
import os
import uuid

import httpx
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

load_dotenv()

app = FastAPI(title="Paperclip ↔ ADK Bridge")


# ── Request model ────────────────────────────────────────────────────────────

class HeartbeatContext(BaseModel):
    taskId: str | None = None
    wakeReason: str = "on_demand"
    commentId: str | None = None


class HeartbeatPayload(BaseModel):
    runId: str
    agentId: str
    companyId: str
    context: HeartbeatContext


# ── ADK runner (shared, initialised once) ───────────────────────────────────

_runner = None
_session_service = None
APP_NAME = "sales-agent-team"


async def _get_runner():
    global _runner, _session_service
    if _runner is None:
        from google.adk.runners import Runner
        from google.adk.sessions import InMemorySessionService
        from agents.company_orchestrator_agent import company_orchestrator

        _session_service = InMemorySessionService()
        _runner = Runner(
            agent=company_orchestrator,
            app_name=APP_NAME,
            session_service=_session_service,
        )
    return _runner, _session_service


async def _run_agent(prompt: str, session_id: str) -> str:
    """Run the ADK agent and return its final text response."""
    from google.genai.types import Content, Part

    runner, session_service = await _get_runner()

    # Create a fresh session for this task
    await session_service.create_session(
        app_name=APP_NAME,
        user_id="paperclip",
        session_id=session_id,
    )

    content = Content(role="user", parts=[Part(text=prompt)])
    final_text = ""

    async for event in runner.run_async(
        user_id="paperclip",
        session_id=session_id,
        new_message=content,
    ):
        if event.is_final_response() and event.content and event.content.parts:
            final_text = event.content.parts[0].text

    return final_text or "(no response)"


# ── Paperclip API helpers (same-process, avoids importing the sync client) ──

def _paperclip_headers() -> dict:
    key = os.environ.get("PAPERCLIP_API_KEY", "")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def _paperclip_url(path: str) -> str:
    base = os.environ.get("PAPERCLIP_API_URL", "http://localhost:3100")
    return f"{base}{path}"


# ── Health check ─────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": "paperclip-adk-bridge"}


# ── Webhook endpoint ──────────────────────────────────────────────────────────

@app.post("/webhook")
async def handle_heartbeat(payload: HeartbeatPayload):
    """
    Paperclip HTTP adapter endpoint.
    Configure agent adapter URL as: http://localhost:8080/webhook
    """
    run_id = payload.runId
    agent_id = payload.agentId
    task_id = payload.context.taskId
    wake_reason = payload.context.wakeReason

    # No task assigned — nothing to do
    if not task_id:
        return JSONResponse({"status": "idle", "reason": f"woke up ({wake_reason}) with no task"})

    async with httpx.AsyncClient(headers=_paperclip_headers(), timeout=30) as client:
        # 1. Fetch issue
        issue_resp = await client.get(_paperclip_url(f"/api/issues/{task_id}"))
        if issue_resp.status_code == 404:
            return JSONResponse({"status": "skipped", "reason": "issue not found"})
        issue_resp.raise_for_status()
        issue = issue_resp.json()

        title = issue.get("title", "Untitled task")
        description = issue.get("description") or ""

        # 2. Checkout (claim) the issue atomically
        checkout_resp = await client.post(
            _paperclip_url(f"/api/issues/{task_id}/checkout"),
            headers={**_paperclip_headers(), "X-Paperclip-Run-Id": run_id},
            json={"agentId": agent_id, "expectedStatuses": ["todo", "backlog", "blocked"]},
        )
        if checkout_resp.status_code == 409:
            return JSONResponse({"status": "skipped", "reason": "issue already claimed"})
        checkout_resp.raise_for_status()

        # 3. Build prompt from issue
        prompt = f"{title}\n\n{description}".strip()

        # 4. Run ADK agent
        session_id = f"paperclip-{task_id}-{uuid.uuid4().hex[:8]}"
        try:
            result = await _run_agent(prompt, session_id)
        except Exception as exc:
            # Release checkout so another agent can retry
            await client.post(_paperclip_url(f"/api/issues/{task_id}/release"))
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        # 5. Post result as comment
        await client.post(
            _paperclip_url(f"/api/issues/{task_id}/comments"),
            json={"body": result},
        )

        # 6. Mark done
        await client.patch(
            _paperclip_url(f"/api/issues/{task_id}"),
            json={"status": "done"},
        )

    return JSONResponse({
        "status": "completed",
        "taskId": task_id,
        "sessionId": session_id,
    })


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PAPERCLIP_WEBHOOK_PORT", "8080"))
    uvicorn.run("paperclip_webhook:app", host="0.0.0.0", port=port, reload=False)
