"""
Root conftest.py — isolates pytest from the ADK agent import chain.

This conftest stubs out the google.adk namespace before pytest starts
collecting tests so smoke tests can import agent modules in isolation.
"""
import sys
from unittest.mock import MagicMock

# Prevent __init__.py from auto-importing the full agent hierarchy
# (which would cause cascading import errors during pytest collection)
sys.modules["__main__"].__spec__ = None


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


# Make Agent constructor return an object with the correct name attribute
def _make_agent_constructor():
    def Agent(model, name, description, instruction, tools=None, sub_agents=None, **kwargs):
        agent = MagicMock()
        agent.name = name
        agent.sub_agents = sub_agents or []
        return agent
    return Agent


sys.modules["google.adk.agents"].Agent = _make_agent_constructor()
