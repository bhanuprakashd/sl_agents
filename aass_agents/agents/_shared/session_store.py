# aass_agents/agents/_shared/session_store.py
"""
Persistent session store — replaces InMemorySessionService with DatabaseSessionService.

Provides:
  - SQLite-backed session persistence (survives restarts)
  - Resume-from-checkpoint: reload a session by ID and continue the pipeline
  - Session listing for the dashboard

Usage:
    from agents._shared.session_store import get_session_service, SESSION_DB_URL

    # In api.py or runner code:
    session_service = get_session_service()
    runner = Runner(agent=root_agent, app_name=APP_NAME, session_service=session_service)

Environment variables:
    SESSION_DB_URL   — SQLAlchemy connection string (default: sqlite+aiosqlite:///./sessions.db)
    SESSION_DURABLE  — set to "0" to use InMemorySessionService (default: "1")
"""
import os
import logging

_log = logging.getLogger(__name__)

SESSION_DB_URL = os.getenv(
    "SESSION_DB_URL",
    "sqlite+aiosqlite:///./sessions.db",
)

_SESSION_DURABLE = os.getenv("SESSION_DURABLE", "1") != "0"


def get_session_service():
    """
    Return the session service — DatabaseSessionService for persistence,
    or InMemorySessionService as fallback.
    """
    if _SESSION_DURABLE:
        try:
            from google.adk.sessions import DatabaseSessionService
            svc = DatabaseSessionService(db_url=SESSION_DB_URL)
            _log.info("Session store: DatabaseSessionService at %s", SESSION_DB_URL)
            return svc
        except Exception as exc:
            _log.warning(
                "Session store: Failed to init DatabaseSessionService (%s), "
                "falling back to InMemorySessionService", exc,
            )

    from google.adk.sessions import InMemorySessionService
    _log.info("Session store: InMemorySessionService (no persistence)")
    return InMemorySessionService()


async def list_sessions(session_service, app_name: str, user_id: str) -> list[dict]:
    """
    List all sessions for a user. Returns dicts with session metadata.

    For DatabaseSessionService, this queries the DB directly.
    For InMemorySessionService, returns sessions from memory.
    """
    try:
        result = await session_service.list_sessions(
            app_name=app_name, user_id=user_id,
        )
        sessions = []
        for s in result.sessions:
            sessions.append({
                "session_id": s.id,
                "app_name": s.app_name,
                "user_id": s.user_id,
                "state_keys": list(s.state.keys()) if s.state else [],
                "event_count": len(s.events) if s.events else 0,
                "last_update": s.last_update_time if hasattr(s, "last_update_time") else None,
            })
        return sessions
    except Exception as exc:
        _log.warning("list_sessions failed: %s", exc)
        return []


async def get_session_state(session_service, app_name: str, user_id: str, session_id: str) -> dict:
    """
    Get the full state dict for a session. Useful for inspecting pipeline progress.
    """
    try:
        session = await session_service.get_session(
            app_name=app_name, user_id=user_id, session_id=session_id,
        )
        if session is None:
            return {"error": f"Session {session_id} not found"}
        return {
            "session_id": session.id,
            "state": dict(session.state) if session.state else {},
            "event_count": len(session.events) if session.events else 0,
        }
    except Exception as exc:
        return {"error": str(exc)}


def get_checkpoint_stages(state: dict) -> dict:
    """
    Analyze session state to determine which pipeline stages have completed.

    Returns:
        {
            "completed": ["setup", "pm", "architect", ...],
            "next": "builder" or None,
            "can_resume": True/False,
        }
    """
    stage_keys = [
        ("setup", "setup_output"),
        ("pm", "prd_output"),
        ("architect", "architecture_output"),
        ("db", "db_output"),
        ("backend", "backend_output"),
        ("frontend", "frontend_output"),
        ("qa", "qa_output"),
        ("ship", "ship_output"),
    ]

    completed = []
    next_stage = None

    for stage_name, state_key in stage_keys:
        if state.get(state_key):
            completed.append(stage_name)
        elif next_stage is None:
            next_stage = stage_name

    return {
        "completed": completed,
        "next": next_stage,
        "can_resume": len(completed) > 0 and next_stage is not None,
    }
