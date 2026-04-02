"""
Progress Callbacks — push-based event broadcasting for real-time dashboards.

Replaces the SQLite polling pattern in build_progress.py with async queues.
Subscribers get instant updates; SQLite remains the durable backing store.

Granular event taxonomy (borrowed from open-multi-agent StreamEvent pattern):
  - agent.started     Agent begins execution
  - agent.text        Agent produced text output (streaming chunk)
  - agent.tool_use    Agent is calling a tool
  - agent.tool_result Tool returned a result
  - agent.completed   Agent finished successfully
  - agent.failed      Agent encountered an error
  - build.phase       Build pipeline phase change (starting/running/completed/failed)
  - pipeline.started  Pipeline run began
  - pipeline.wave     A parallel wave started
  - pipeline.completed Pipeline finished
  - pipeline.failed   Pipeline encountered a fatal error
  - system.error      System-level error
  - system.done       Stream complete (terminal event)

Usage:
    from tools.progress_callbacks import broadcaster, EventType

    # Emit (from tools/agents):
    await broadcaster.emit("product-123", "scaffold", "completed", "Done!")

    # Subscribe (from SSE endpoint):
    async for event in broadcaster.subscribe("product-123"):
        yield f"data: {json.dumps(event)}\\n\\n"
"""
import asyncio
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import AsyncIterator, Optional


class EventType(str, Enum):
    """Granular event taxonomy for streaming."""
    # Agent lifecycle
    AGENT_STARTED = "agent.started"
    AGENT_TEXT = "agent.text"
    AGENT_TOOL_USE = "agent.tool_use"
    AGENT_TOOL_RESULT = "agent.tool_result"
    AGENT_COMPLETED = "agent.completed"
    AGENT_FAILED = "agent.failed"
    # Build phases
    BUILD_PHASE = "build.phase"
    # Pipeline lifecycle
    PIPELINE_STARTED = "pipeline.started"
    PIPELINE_WAVE = "pipeline.wave"
    PIPELINE_COMPLETED = "pipeline.completed"
    PIPELINE_FAILED = "pipeline.failed"
    # System
    SYSTEM_ERROR = "system.error"
    SYSTEM_DONE = "system.done"


@dataclass(frozen=True)
class StreamEvent:
    """Immutable streaming event with granular type."""
    product_id: str
    event_type: str
    agent_name: str
    phase: str
    status: str
    message: str
    output_preview: str
    timestamp: str
    # Optional structured data for tool events
    tool_name: str = ""
    tool_args: str = ""       # JSON string
    tool_result: str = ""     # Truncated result
    wave_index: int = -1      # For pipeline.wave events
    duration_ms: int = 0
    token_count: int = 0      # For agent.text events (chars streamed so far)

    def to_dict(self) -> dict:
        d = {
            "product_id": self.product_id,
            "event_type": self.event_type,
            "agent_name": self.agent_name,
            "phase": self.phase,
            "status": self.status,
            "message": self.message,
            "timestamp": self.timestamp,
        }
        # Only include non-empty optional fields
        if self.output_preview:
            d["output_preview"] = self.output_preview
        if self.tool_name:
            d["tool_name"] = self.tool_name
        if self.tool_args:
            d["tool_args"] = self.tool_args
        if self.tool_result:
            d["tool_result"] = self.tool_result
        if self.wave_index >= 0:
            d["wave_index"] = self.wave_index
        if self.duration_ms > 0:
            d["duration_ms"] = self.duration_ms
        if self.token_count > 0:
            d["token_count"] = self.token_count
        return d


# Backward compat alias
ProgressEvent = StreamEvent


class ProgressBroadcaster:
    """
    Fan-out broadcaster using asyncio.Queue per subscriber.

    Thread-safe for emit (uses call_soon_threadsafe when called from sync context).
    Subscribers must run in an asyncio event loop.
    """

    def __init__(self) -> None:
        # product_id -> set of subscriber queues
        self._product_subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)
        # Global subscribers (receive ALL events)
        self._global_subscribers: set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()

    async def subscribe(
        self,
        product_id: Optional[str] = None,
        max_queue: int = 100,
    ) -> AsyncIterator[dict]:
        """
        Yield progress events as dicts. If product_id is None, subscribes globally.
        Automatically cleans up on generator exit.
        """
        queue: asyncio.Queue = asyncio.Queue(maxsize=max_queue)

        async with self._lock:
            if product_id:
                self._product_subscribers[product_id].add(queue)
            else:
                self._global_subscribers.add(queue)

        try:
            while True:
                event = await queue.get()
                if event is None:  # poison pill
                    break
                yield event
        finally:
            async with self._lock:
                if product_id:
                    self._product_subscribers[product_id].discard(queue)
                    if not self._product_subscribers[product_id]:
                        del self._product_subscribers[product_id]
                else:
                    self._global_subscribers.discard(queue)

    async def emit(
        self,
        product_id: str,
        phase: str,
        status: str,
        message: str = "",
        output_preview: str = "",
        agent_name: str = "",
        event_type: str = "build.phase",
        tool_name: str = "",
        tool_args: str = "",
        tool_result: str = "",
        wave_index: int = -1,
        duration_ms: int = 0,
        token_count: int = 0,
    ) -> None:
        """Push a granular event to all subscribers for this product + all global subscribers."""
        event = StreamEvent(
            product_id=product_id,
            phase=phase,
            status=status,
            message=message,
            output_preview=output_preview[:500],
            agent_name=agent_name,
            event_type=event_type,
            timestamp=datetime.now(timezone.utc).isoformat(),
            tool_name=tool_name,
            tool_args=tool_args,
            tool_result=tool_result[:600] if tool_result else "",
            wave_index=wave_index,
            duration_ms=duration_ms,
            token_count=token_count,
        )
        event_dict = event.to_dict()

        async with self._lock:
            targets = set(self._product_subscribers.get(product_id, set()))
            targets.update(self._global_subscribers)

        for queue in targets:
            try:
                queue.put_nowait(event_dict)
            except asyncio.QueueFull:
                # Drop oldest event if queue is full (prevent memory leak)
                try:
                    queue.get_nowait()
                    queue.put_nowait(event_dict)
                except asyncio.QueueEmpty:
                    pass

    def emit_sync(
        self,
        product_id: str,
        phase: str,
        status: str,
        message: str = "",
        output_preview: str = "",
        agent_name: str = "",
        event_type: str = "build.phase",
    ) -> None:
        """Sync wrapper for emit — safe to call from non-async tool functions."""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.emit(
                product_id, phase, status, message,
                output_preview, agent_name, event_type,
            ))
        except RuntimeError:
            pass  # No event loop — skip broadcast (CLI mode)

    async def emit_agent_event(
        self,
        run_id: str,
        agent_name: str,
        event_type: str,
        message: str = "",
        duration_ms: int = 0,
    ) -> None:
        """Emit an agent lifecycle event (started/completed/failed)."""
        await self.emit(
            product_id=run_id,
            phase=agent_name,
            status=event_type.split(".")[-1],
            message=message,
            agent_name=agent_name,
            event_type=event_type,
            duration_ms=duration_ms,
        )

    async def emit_tool_event(
        self,
        run_id: str,
        agent_name: str,
        tool_name: str,
        tool_args: str = "",
        tool_result: str = "",
        is_result: bool = False,
    ) -> None:
        """Emit a tool_use or tool_result event."""
        etype = EventType.AGENT_TOOL_RESULT if is_result else EventType.AGENT_TOOL_USE
        await self.emit(
            product_id=run_id,
            phase=agent_name,
            status="tool_result" if is_result else "tool_use",
            agent_name=agent_name,
            event_type=etype.value,
            tool_name=tool_name,
            tool_args=tool_args,
            tool_result=tool_result,
        )

    async def emit_text(
        self,
        run_id: str,
        agent_name: str,
        text: str,
        token_count: int = 0,
    ) -> None:
        """Emit a streaming text chunk from an agent."""
        await self.emit(
            product_id=run_id,
            phase=agent_name,
            status="streaming",
            message=text[:200],
            agent_name=agent_name,
            event_type=EventType.AGENT_TEXT.value,
            token_count=token_count,
        )

    async def emit_pipeline_event(
        self,
        run_id: str,
        event_type: str,
        message: str = "",
        wave_index: int = -1,
    ) -> None:
        """Emit a pipeline lifecycle event."""
        await self.emit(
            product_id=run_id,
            phase="pipeline",
            status=event_type.split(".")[-1],
            message=message,
            event_type=event_type,
            wave_index=wave_index,
        )

    async def close_product(self, product_id: str) -> None:
        """Send poison pill to all subscribers for a product."""
        async with self._lock:
            queues = self._product_subscribers.pop(product_id, set())
        for queue in queues:
            try:
                queue.put_nowait(None)
            except asyncio.QueueFull:
                pass


# Module-level singleton
broadcaster = ProgressBroadcaster()
