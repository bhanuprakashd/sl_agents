"""
Hook Engine — declarative, configuration-driven lifecycle hooks.

Replaces hardcoded callbacks in main.py with a YAML-driven hook system.
Inspired by Claude Code's hook system with 15+ event types.

Supported events:
  - pre_agent:   Before ADK dispatches any agent call
  - post_agent:  After ADK gets the agent's response
  - pre_tool:    Before a tool executes
  - post_tool:   After a tool executes
  - task_start:  When a pipeline run starts
  - task_end:    When a pipeline run completes/fails
  - error:       When an unhandled error occurs

Hooks are defined in hooks.yaml and executed in order.
Handlers are resolved from dotted module paths.
"""
import importlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HookDef:
    """Definition of a single hook."""
    event: str
    handler: str       # Dotted path: "module.function" or "module.Class.method"
    description: str = ""
    agents: Optional[tuple[str, ...]] = None  # Filter: only fire for these agents
    priority: int = 100  # Lower = runs first


class HookEngine:
    """
    Configuration-driven hook dispatcher.

    Loads hook definitions from YAML. Fires hooks in priority order.
    Thread-safe for reads (immutable after load). Call reload() to update.
    """

    def __init__(self, config_path: Optional[str] = None) -> None:
        self._hooks: dict[str, list[HookDef]] = {}
        self._resolved: dict[str, callable] = {}  # Cache: handler path -> callable
        if config_path:
            self.load(config_path)

    def load(self, config_path: str) -> None:
        """Load hooks from a YAML config file."""
        path = Path(config_path)
        if not path.exists():
            logger.warning("Hook config not found: %s", config_path)
            return

        with open(path, "r") as f:
            config = yaml.safe_load(f)

        if not config or "hooks" not in config:
            return

        new_hooks: dict[str, list[HookDef]] = {}
        for hook_data in config["hooks"]:
            event = hook_data["event"]
            agents_raw = hook_data.get("agents")
            agents = tuple(agents_raw) if agents_raw else None

            hook = HookDef(
                event=event,
                handler=hook_data["handler"],
                description=hook_data.get("description", ""),
                agents=agents,
                priority=hook_data.get("priority", 100),
            )

            if event not in new_hooks:
                new_hooks[event] = []
            new_hooks[event].append(hook)

        # Sort each event's hooks by priority
        for event in new_hooks:
            new_hooks[event].sort(key=lambda h: h.priority)

        self._hooks = new_hooks
        self._resolved.clear()
        logger.info("Loaded %d hooks across %d events",
                     sum(len(v) for v in new_hooks.values()), len(new_hooks))

    def reload(self, config_path: str) -> None:
        """Reload hooks from config (hot-reload)."""
        self.load(config_path)

    def register(self, hook: HookDef) -> None:
        """Programmatically register a hook (for runtime additions)."""
        if hook.event not in self._hooks:
            self._hooks[hook.event] = []
        self._hooks[hook.event].append(hook)
        self._hooks[hook.event].sort(key=lambda h: h.priority)

    def _resolve_handler(self, handler_path: str) -> Optional[callable]:
        """Resolve a dotted path to a callable."""
        if handler_path in self._resolved:
            return self._resolved[handler_path]

        try:
            parts = handler_path.rsplit(".", 1)
            if len(parts) != 2:
                logger.error("Invalid handler path: %s", handler_path)
                return None

            module_path, attr_name = parts

            # Try direct module.function first
            try:
                mod = importlib.import_module(module_path)
                func = getattr(mod, attr_name)
                self._resolved[handler_path] = func
                return func
            except (ImportError, AttributeError):
                pass

            # Try module.Class.method
            parts = handler_path.rsplit(".", 2)
            if len(parts) == 3:
                mod = importlib.import_module(parts[0])
                cls = getattr(mod, parts[1])
                func = getattr(cls, parts[2])
                self._resolved[handler_path] = func
                return func

        except Exception as exc:
            logger.error("Failed to resolve handler %s: %s", handler_path, exc)

        return None

    def fire(self, event: str, context: dict) -> list[Any]:
        """
        Fire all hooks for an event.

        Args:
            event: Event name (e.g., "pre_agent", "post_agent")
            context: Dict with event data (run_id, agent_name, input_text, etc.)

        Returns:
            List of hook return values. If any hook returns a non-None value
            that is a Content object, it can be used to block agent execution.
        """
        hooks = self._hooks.get(event, [])
        if not hooks:
            return []

        results: list[Any] = []
        agent_name = context.get("agent_name", "")

        for hook in hooks:
            # Check agent filter
            if hook.agents and agent_name not in hook.agents:
                continue

            handler = self._resolve_handler(hook.handler)
            if handler is None:
                logger.warning("Skipping unresolvable hook: %s", hook.handler)
                continue

            try:
                result = handler(context)
                results.append(result)
            except Exception as exc:
                logger.error("Hook %s failed: %s", hook.handler, exc)
                results.append(None)

        return results

    def list_hooks(self) -> list[dict]:
        """List all registered hooks (for API/dashboard)."""
        all_hooks = []
        for event, hooks in sorted(self._hooks.items()):
            for hook in hooks:
                all_hooks.append({
                    "event": hook.event,
                    "handler": hook.handler,
                    "description": hook.description,
                    "agents": list(hook.agents) if hook.agents else None,
                    "priority": hook.priority,
                })
        return all_hooks

    def get_events(self) -> list[str]:
        """List all event types that have hooks registered."""
        return sorted(self._hooks.keys())
