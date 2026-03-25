"""
Root conftest.py — isolates pytest from the ADK agent import chain.

This conftest stubs out the google.adk namespace before pytest starts
collecting tests so smoke tests can import agent modules in isolation.
"""
import sys
from unittest.mock import MagicMock, AsyncMock

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


# Make InMemorySessionService return an instance with async methods
def _make_session_service_constructor():
    def InMemorySessionService():
        svc = MagicMock()
        svc.create_session = AsyncMock(return_value=MagicMock())
        svc.get_session = AsyncMock(return_value=MagicMock())
        svc.delete_session = AsyncMock(return_value=None)
        return svc
    return InMemorySessionService


sys.modules["google.adk.sessions"].InMemorySessionService = _make_session_service_constructor()


# Make Runner.run_async an async generator that yields a final response event
async def _async_gen_run(*args, **kwargs):
    event = MagicMock()
    event.is_final_response = MagicMock(return_value=True)
    event.content = MagicMock()
    event.content.parts = [MagicMock(text="mock response")]
    yield event


def _make_runner_constructor():
    def Runner(agent, app_name, session_service):
        runner = MagicMock()
        runner.run_async = _async_gen_run
        return runner
    return Runner


sys.modules["google.adk.runners"].Runner = _make_runner_constructor()
