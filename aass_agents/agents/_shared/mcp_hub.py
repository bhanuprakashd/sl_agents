# aass_agents/agents/_shared/mcp_hub.py
"""
MCP Hub — single gateway for all agents to access external MCP servers.

Any agent in the system can request tools by capability. The hub manages
connections, avoids duplicates, and provides a unified interface to the
5000+ MCP server ecosystem.

Usage in agent definitions:
    from agents._shared.mcp_hub import mcp_hub

    architect_agent = Agent(
        tools=[
            mcp_hub.get_toolset("packages"),   # npm/PyPI/crates search
            mcp_hub.get_toolset("docs"),        # live documentation
            mcp_hub.get_toolset("github"),      # GitHub repos, issues, code
            ...other tools...
        ],
    )

    # Or get multiple at once:
    tools = mcp_hub.get_toolsets(["packages", "docs", "browser"])

Configuration:
    MCP servers are registered in mcp_hub_config.yaml alongside this file.
    Each server declares its capability tag, connection type, and optional
    tool_filter to expose only relevant tools.

    Servers with missing env vars or disabled=true are silently skipped.

Environment variables:
    MCP_HUB_ENABLED  — set to "0" to disable all MCP servers (default: "1")
    MCP_HUB_CONFIG   — path to config YAML (default: mcp_hub_config.yaml)
"""

import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

_log = logging.getLogger(__name__)

MCP_HUB_ENABLED = os.getenv("MCP_HUB_ENABLED", "1") != "0"
_CONFIG_PATH = Path(os.getenv(
    "MCP_HUB_CONFIG",
    Path(__file__).parent / "mcp_hub_config.yaml",
))


# ── Server definition ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class McpServerDef:
    """Immutable definition of an MCP server from config."""
    name: str
    capability: str
    description: str
    connection_type: str            # "stdio" | "sse" | "http"
    command: Optional[str] = None   # stdio: executable
    args: tuple = ()                # stdio: arguments
    url: Optional[str] = None       # sse/http: endpoint URL
    env_keys: tuple = ()            # required env var names
    tool_filter: Optional[tuple] = None  # limit exposed tools
    tool_prefix: Optional[str] = None    # prefix to avoid collisions
    headers_env: dict = field(default_factory=dict)  # header name → env var name
    disabled: bool = False


# ── Hub singleton ────────────────────────────────────────────────────────────

class McpHub:
    """
    Central registry of MCP servers. Agents request toolsets by capability.

    - Lazy: connections are only created when first requested
    - Cached: same capability returns the same McpToolset instance
    - Safe: missing env vars or disabled servers are silently skipped
    """

    def __init__(self):
        self._server_defs: dict[str, McpServerDef] = {}
        self._toolset_cache: dict[str, object] = {}
        self._loaded = False

    def _load_config(self):
        """Load server definitions from YAML config."""
        if self._loaded:
            return
        self._loaded = True

        if not MCP_HUB_ENABLED:
            _log.info("MCP Hub: Disabled via MCP_HUB_ENABLED=0")
            return

        if not _CONFIG_PATH.exists():
            _log.warning("MCP Hub: Config not found at %s", _CONFIG_PATH)
            return

        raw = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8"))
        servers = raw.get("servers", [])

        for s in servers:
            if s.get("disabled", False):
                continue

            name = s["name"]
            env_keys = tuple(s.get("env_keys", []))

            # Check if required env vars are present
            missing = [k for k in env_keys if not os.getenv(k)]
            if missing:
                _log.debug("MCP Hub: Skipping '%s' — missing env: %s", name, missing)
                continue

            self._server_defs[s["capability"]] = McpServerDef(
                name=name,
                capability=s["capability"],
                description=s.get("description", ""),
                connection_type=s.get("connection_type", "stdio"),
                command=s.get("command"),
                args=tuple(s.get("args", [])),
                url=s.get("url"),
                env_keys=env_keys,
                tool_filter=tuple(s["tool_filter"]) if s.get("tool_filter") else None,
                tool_prefix=s.get("tool_prefix"),
                headers_env=s.get("headers_env", {}),
                disabled=False,
            )

        _log.info(
            "MCP Hub: Loaded %d servers: %s",
            len(self._server_defs),
            list(self._server_defs.keys()),
        )

    def _create_toolset(self, server_def: McpServerDef):
        """Create an McpToolset for a server definition."""
        from google.adk.tools.mcp_tool.mcp_toolset import McpToolset

        kwargs = {}
        if server_def.tool_filter:
            kwargs["tool_filter"] = list(server_def.tool_filter)
        if server_def.tool_prefix:
            kwargs["tool_name_prefix"] = server_def.tool_prefix

        if server_def.connection_type == "stdio":
            from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
            from mcp import StdioServerParameters

            env = {**os.environ}
            for key in server_def.env_keys:
                val = os.getenv(key)
                if val:
                    env[key] = val

            connection_params = StdioConnectionParams(
                server_params=StdioServerParameters(
                    command=server_def.command,
                    args=list(server_def.args),
                    env=env,
                ),
                timeout=30.0,
            )

        elif server_def.connection_type in ("sse", "http"):
            from google.adk.tools.mcp_tool.mcp_session_manager import SseConnectionParams

            headers = {}
            for header_name, env_var in server_def.headers_env.items():
                val = os.getenv(env_var)
                if val:
                    headers[header_name] = val

            connection_params = SseConnectionParams(
                url=server_def.url,
                headers=headers if headers else None,
            )
        else:
            raise ValueError(f"Unknown connection_type: {server_def.connection_type}")

        toolset = McpToolset(connection_params=connection_params, **kwargs)
        _log.info("MCP Hub: Connected '%s' (%s)", server_def.name, server_def.capability)
        return toolset

    def get_toolset(self, capability: str):
        """
        Get an McpToolset by capability name.

        Returns the toolset if the server is configured and env vars are present,
        or None if unavailable. Agents should handle None gracefully.

        Args:
            capability: e.g. "github", "packages", "docs", "browser", "search"

        Returns:
            McpToolset instance or None
        """
        self._load_config()

        if capability in self._toolset_cache:
            return self._toolset_cache[capability]

        server_def = self._server_defs.get(capability)
        if not server_def:
            _log.debug("MCP Hub: No server registered for capability '%s'", capability)
            return None

        try:
            toolset = self._create_toolset(server_def)
            self._toolset_cache[capability] = toolset
            return toolset
        except Exception as exc:
            _log.warning("MCP Hub: Failed to connect '%s': %s", capability, exc)
            return None

    def get_toolsets(self, capabilities: list[str]) -> list:
        """
        Get multiple McpToolsets by capability. Skips unavailable ones.

        Args:
            capabilities: e.g. ["github", "packages", "docs"]

        Returns:
            List of McpToolset instances (only those that connected successfully)
        """
        toolsets = []
        for cap in capabilities:
            ts = self.get_toolset(cap)
            if ts is not None:
                toolsets.append(ts)
        return toolsets

    def list_available(self) -> list[dict]:
        """List all available (configured + env vars present) MCP servers."""
        self._load_config()
        return [
            {
                "capability": sd.capability,
                "name": sd.name,
                "description": sd.description,
                "connection_type": sd.connection_type,
                "connected": sd.capability in self._toolset_cache,
            }
            for sd in self._server_defs.values()
        ]

    def list_all_capabilities(self) -> list[str]:
        """List all registered capability names."""
        self._load_config()
        return list(self._server_defs.keys())


# ── Singleton ────────────────────────────────────────────────────────────────
mcp_hub = McpHub()
