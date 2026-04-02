"""
Tool Registry — runtime tool discovery with capability-based lookup.

Replaces hardcoded tool lists with a searchable registry. Agents can
discover tools by capability ("research", "build", "memory") or department.

Inspired by Claude Code's ToolSearchTool dynamic discovery pattern.
"""
import importlib
import inspect
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass(frozen=True)
class ToolEntry:
    """Metadata about a registered tool."""
    name: str
    function: Optional[callable]
    capabilities: tuple[str, ...]
    departments: tuple[str, ...]
    tier: str  # "fast", "std", "deep"
    description: str
    module: str = ""


class ToolRegistry:
    """
    Runtime tool registry with capability-based lookup.

    Register tools manually or load from YAML config.
    Query by capability, department, or name.
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolEntry] = {}

    def register(self, entry: ToolEntry) -> None:
        """Register a tool entry."""
        self._tools[entry.name] = entry

    def get(self, name: str) -> Optional[ToolEntry]:
        """Get a tool entry by name."""
        return self._tools.get(name)

    def find_by_capability(self, *capabilities: str) -> list[ToolEntry]:
        """Find tools that have ALL specified capabilities."""
        cap_set = set(capabilities)
        return [
            entry for entry in self._tools.values()
            if cap_set.issubset(set(entry.capabilities))
        ]

    def find_by_any_capability(self, *capabilities: str) -> list[ToolEntry]:
        """Find tools that have ANY of the specified capabilities."""
        cap_set = set(capabilities)
        return [
            entry for entry in self._tools.values()
            if cap_set.intersection(set(entry.capabilities))
        ]

    def find_by_department(self, department: str) -> list[ToolEntry]:
        """Find tools available to a department."""
        return [
            entry for entry in self._tools.values()
            if department in entry.departments or "all" in entry.departments
        ]

    def get_tools_for_agent(self, agent_name: str, department: str = "") -> list[callable]:
        """Get callable tool functions for an agent based on its department."""
        entries = self.find_by_department(department) if department else list(self._tools.values())
        return [e.function for e in entries if e.function is not None]

    def get_tool_names_for_capabilities(self, *capabilities: str) -> list[str]:
        """Get tool names matching capabilities (for use with tool_mask)."""
        entries = self.find_by_any_capability(*capabilities)
        return [e.name for e in entries]

    def list_all(self) -> list[ToolEntry]:
        """List all registered tools."""
        return list(self._tools.values())

    def list_capabilities(self) -> list[str]:
        """List all unique capabilities across all tools."""
        caps: set[str] = set()
        for entry in self._tools.values():
            caps.update(entry.capabilities)
        return sorted(caps)

    def load_from_yaml(self, config_path: str) -> None:
        """
        Load tool metadata from a YAML config file.
        Maps tool names to capabilities, departments, and tiers.
        Auto-resolves function references from modules.
        """
        path = Path(config_path)
        if not path.exists():
            return

        with open(path, "r") as f:
            config = yaml.safe_load(f)

        if not config or "tools" not in config:
            return

        for tool_name, meta in config["tools"].items():
            func = None
            module_path = meta.get("module", "")

            if module_path:
                try:
                    mod = importlib.import_module(module_path)
                    func = getattr(mod, tool_name, None)
                except (ImportError, AttributeError):
                    pass

            entry = ToolEntry(
                name=tool_name,
                function=func,
                capabilities=tuple(meta.get("capabilities", [])),
                departments=tuple(meta.get("departments", ["all"])),
                tier=meta.get("tier", "std"),
                description=meta.get("description", ""),
                module=module_path,
            )
            self.register(entry)

    def auto_discover(self, tools_dir: str) -> None:
        """
        Auto-discover tool functions from Python modules in a directory.
        Only registers functions not already in the registry.
        """
        tools_path = Path(tools_dir)
        if not tools_path.is_dir():
            return

        for py_file in tools_path.glob("*.py"):
            if py_file.name.startswith("_"):
                continue

            module_name = f"tools.{py_file.stem}"
            try:
                mod = importlib.import_module(module_name)
            except ImportError:
                continue

            for name, obj in inspect.getmembers(mod, inspect.isfunction):
                if name.startswith("_"):
                    continue
                if name in self._tools:
                    continue  # Already registered via YAML

                doc = inspect.getdoc(obj) or ""
                if not doc:
                    continue  # Skip undocumented functions

                entry = ToolEntry(
                    name=name,
                    function=obj,
                    capabilities=("general",),
                    departments=("all",),
                    tier="std",
                    description=doc.split("\n")[0],
                    module=module_name,
                )
                self.register(entry)


# ── Module-level singleton ───────────────────────────────────────────────────

registry = ToolRegistry()


# ── ADK Tool Function ────────────────────────────────────────────────────────

def discover_tools(capability: str, department: str = "") -> str:
    """
    Discover available tools by capability or department.

    Args:
        capability: Tool capability to search for (e.g., "research", "build", "memory", "browser")
        department: Optional department filter (e.g., "sales", "product", "engineering")

    Returns:
        JSON list of matching tools with names and descriptions
    """
    if department:
        entries = [
            e for e in registry.find_by_any_capability(capability)
            if department in e.departments or "all" in e.departments
        ]
    else:
        entries = registry.find_by_any_capability(capability)

    if not entries:
        all_caps = registry.list_capabilities()
        return json.dumps({
            "matches": [],
            "hint": f"No tools found for capability '{capability}'. Available capabilities: {all_caps}",
        })

    return json.dumps({
        "matches": [
            {
                "name": e.name,
                "description": e.description,
                "capabilities": list(e.capabilities),
                "tier": e.tier,
            }
            for e in entries
        ],
        "count": len(entries),
    }, indent=2)
