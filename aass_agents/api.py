"""
SL Agents — FastAPI backend for the dashboard UI.

Serves the dashboard and streams ADK agent events via SSE.

Run:
    uvicorn api:app --reload --port 8080

Then open: http://localhost:8080
"""

import asyncio
import json
import os
import uuid
from pathlib import Path
from typing import AsyncGenerator

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part

from main import root_agent
from tools.supervisor_db import init_supervisor_tables

init_supervisor_tables()

app = FastAPI(title="SL Agents API", docs_url="/api/docs")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

APP_NAME = "sl-agents-ui"
_session_service = InMemorySessionService()

GENERATED_SKILLS_PATH = Path(__file__).parent.parent / "generated_skills" / "_registry.json"


# ── Models ────────────────────────────────────────────────────────────────────

class RunRequest(BaseModel):
    prompt: str
    session_id: str | None = None


# ── SSE helpers ───────────────────────────────────────────────────────────────

def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


def _extract_parts(event) -> tuple[str, list[dict], list[dict]]:
    """Return (text, tool_calls, tool_results) from an ADK event."""
    text = ""
    tool_calls = []
    tool_results = []
    if not (event.content and event.content.parts):
        return text, tool_calls, tool_results
    for part in event.content.parts:
        if hasattr(part, "text") and part.text:
            text += part.text
        if hasattr(part, "function_call") and part.function_call:
            fc = part.function_call
            tool_calls.append({
                "name": fc.name,
                "args": dict(fc.args) if fc.args else {},
            })
        if hasattr(part, "function_response") and part.function_response:
            fr = part.function_response
            resp = fr.response
            if isinstance(resp, dict):
                resp_str = json.dumps(resp)[:600]
            else:
                resp_str = str(resp)[:600]
            tool_results.append({"name": fr.name, "result": resp_str})
    return text, tool_calls, tool_results


async def _stream_run(prompt: str, session_id: str) -> AsyncGenerator[str, None]:
    # Create session (ignore if already exists)
    try:
        await _session_service.create_session(
            app_name=APP_NAME, user_id="ui-user", session_id=session_id,
        )
    except Exception:
        pass

    runner = Runner(
        agent=root_agent,
        app_name=APP_NAME,
        session_service=_session_service,
    )

    run_id = str(uuid.uuid4())
    yield _sse({"type": "run_start", "run_id": run_id, "prompt": prompt})

    try:
        async for event in runner.run_async(
            user_id="ui-user",
            session_id=session_id,
            new_message=Content(role="user", parts=[Part(text=prompt)]),
        ):
            author = getattr(event, "author", None) or "unknown"
            text, tool_calls, tool_results = _extract_parts(event)

            for tc in tool_calls:
                yield _sse({"type": "tool_call", "agent": author,
                            "tool": tc["name"], "args": tc["args"]})

            for tr in tool_results:
                yield _sse({"type": "tool_result", "agent": author,
                            "tool": tr["name"], "result": tr["result"]})

            if text:
                if event.is_final_response():
                    yield _sse({"type": "final", "agent": author, "text": text})
                else:
                    yield _sse({"type": "agent_text", "agent": author, "text": text})

        yield _sse({"type": "done"})

    except Exception as exc:
        yield _sse({"type": "error", "message": str(exc)})
        yield _sse({"type": "done"})


# ── Routes ────────────────────────────────────────────────────────────────────

@app.post("/api/run")
async def run_agent(req: RunRequest):
    """Stream agent execution events via SSE."""
    session_id = req.session_id or str(uuid.uuid4())
    return StreamingResponse(
        _stream_run(req.prompt, session_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/skills")
async def get_skills():
    """Return the staged skills registry."""
    if GENERATED_SKILLS_PATH.exists():
        return json.loads(GENERATED_SKILLS_PATH.read_text())
    return {"version": "1.0", "skills": []}


@app.get("/api/status")
async def get_status():
    """Return system status."""
    return {
        "status": "running",
        "model": os.getenv("MODEL_ID", "gemini-2.0-flash"),
        "agent": root_agent.name,
    }


@app.get("/")
async def serve_dashboard():
    return FileResponse("dashboard.html")
