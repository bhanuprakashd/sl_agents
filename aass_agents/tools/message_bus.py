"""
Message Bus — async inter-agent messaging with ADK tool functions.

Combines SQLite persistence (message_bus_db) with asyncio.Condition for
real-time notification. Agents use tool functions to send/receive messages.

Uses contextvars to inject run_id and agent_name (same pattern as cost_tracker).
"""
import asyncio
import contextvars
import json
from typing import Optional

from tools.message_bus_db import (
    init_message_tables,
    send_message as db_send,
    read_messages as db_read,
    peek_messages as db_peek,
    count_pending as db_count,
)

# ── Context vars (set by supervisor callbacks) ───────────────────────────────

_msg_run_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "msg_run_id", default=None
)
_msg_agent_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "msg_agent_name", default=None
)


def set_message_context(run_id: str, agent_name: str) -> None:
    """Set messaging context for the current agent."""
    _msg_run_id_var.set(run_id)
    _msg_agent_var.set(agent_name)


def clear_message_context() -> None:
    """Clear messaging context."""
    _msg_run_id_var.set(None)
    _msg_agent_var.set(None)


# ── Async notification layer ─────────────────────────────────────────────────

class _NotificationHub:
    """Async notification for real-time message delivery."""

    def __init__(self) -> None:
        self._conditions: dict[str, asyncio.Condition] = {}

    def _key(self, run_id: str, agent_name: str) -> str:
        return f"{run_id}:{agent_name}"

    async def notify(self, run_id: str, agent_name: str) -> None:
        """Wake up any waiter for this agent."""
        key = self._key(run_id, agent_name)
        cond = self._conditions.get(key)
        if cond:
            async with cond:
                cond.notify_all()

    async def wait(self, run_id: str, agent_name: str, timeout: float = 30.0) -> bool:
        """Wait for a notification. Returns True if notified, False on timeout."""
        key = self._key(run_id, agent_name)
        if key not in self._conditions:
            self._conditions[key] = asyncio.Condition()
        cond = self._conditions[key]
        try:
            async with cond:
                return await asyncio.wait_for(cond.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            return False


_hub = _NotificationHub()


# ── ADK Tool Functions ───────────────────────────────────────────────────────

def send_agent_message(to_agent: str, msg_type: str, payload: str) -> str:
    """
    Send a message to another agent in the current pipeline run.

    Args:
        to_agent: Name of the recipient agent (e.g., "pm_agent", "architect_agent")
        msg_type: Message type — one of "question", "answer", "notify", "data"
        payload: Message content (text or JSON string)

    Returns:
        Confirmation with message ID
    """
    run_id = _msg_run_id_var.get()
    from_agent = _msg_agent_var.get()

    if not run_id or not from_agent:
        return json.dumps({
            "error": "No active pipeline run. Messages can only be sent during supervised runs."
        })

    try:
        payload_dict = json.loads(payload)
    except (json.JSONDecodeError, TypeError):
        payload_dict = payload

    msg_id = db_send(
        run_id=run_id,
        from_agent=from_agent,
        to_agent=to_agent,
        msg_type=msg_type,
        payload=payload_dict,
    )

    # Try to notify the recipient (async)
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_hub.notify(run_id, to_agent))
    except RuntimeError:
        pass

    return json.dumps({
        "sent": True,
        "message_id": msg_id,
        "from": from_agent,
        "to": to_agent,
        "type": msg_type,
    })


def check_agent_messages() -> str:
    """
    Check for pending messages from other agents.

    Returns:
        JSON with list of pending messages, or empty list if none
    """
    run_id = _msg_run_id_var.get()
    agent_name = _msg_agent_var.get()

    if not run_id or not agent_name:
        return json.dumps({"messages": [], "count": 0})

    messages = db_read(run_id, agent_name, mark_read=True)

    return json.dumps({
        "messages": messages,
        "count": len(messages),
    }, default=str)


def reply_to_agent(original_sender: str, payload: str) -> str:
    """
    Reply to a message from another agent.

    Args:
        original_sender: Name of the agent who sent the original message
        payload: Reply content

    Returns:
        Confirmation
    """
    return send_agent_message(
        to_agent=original_sender,
        msg_type="answer",
        payload=payload,
    )


# ── Init ─────────────────────────────────────────────────────────────────────
init_message_tables()
