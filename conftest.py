"""
Root conftest.py — isolates pytest from the ADK agent import chain.

The root __init__.py imports the full agent hierarchy at module load time,
which triggers a pydantic validation error (reflection_agent assigned two
parent agents). This conftest stubs out the google.adk namespace before
pytest starts collecting tests so tool/utility tests can run in isolation.
"""
import sys
from unittest.mock import MagicMock


def _make_module_mock(name: str) -> MagicMock:
    m = MagicMock()
    m.__name__ = name
    m.__spec__ = None
    return m


# Build a hierarchy of mocks for google.adk and all known sub-paths
# so that `from google.adk.tools.mcp_tool.mcp_toolset import ...` resolves.
_submodules = [
    "google",
    "google.adk",
    "google.adk.agents",
    "google.adk.tools",
    "google.adk.tools.mcp_tool",
    "google.adk.tools.mcp_tool.mcp_toolset",
    "google.adk.runners",
    "google.adk.sessions",
    "google.adk.memory",
    "google.adk.artifacts",
    "google.adk.events",
]

for _mod in _submodules:
    if _mod not in sys.modules:
        sys.modules[_mod] = _make_module_mock(_mod)
