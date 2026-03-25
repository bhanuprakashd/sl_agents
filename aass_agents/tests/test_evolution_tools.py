"""
Unit tests for tools/evolution_tools.py

Focuses on patch_instruction (disk I/O) and get_agent_file_path.
DB operations are tested in test_evolution_db.py.
"""
import os
import pytest
import textwrap
from pathlib import Path

import tools.evolution_db as edb
import tools.evolution_tools as et


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_evo.db"
    monkeypatch.setattr(edb, "EVOLUTION_DB_PATH", db_path)
    edb.init_db()
    yield


# ── get_agent_file_path ───────────────────────────────────────────────────────

def test_get_agent_file_path_existing(tmp_path, monkeypatch):
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "foo_agent.py").write_text("# foo")
    monkeypatch.setattr(et, "_AGENTS_DIR", agents_dir)

    path = et.get_agent_file_path("foo_agent")
    assert path.endswith("foo_agent.py")


def test_get_agent_file_path_missing(tmp_path, monkeypatch):
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    monkeypatch.setattr(et, "_AGENTS_DIR", agents_dir)

    with pytest.raises(FileNotFoundError, match="foo_agent.py"):
        et.get_agent_file_path("foo_agent")


# ── patch_instruction ─────────────────────────────────────────────────────────

def _make_agent_file(tmp_path: Path, instruction: str) -> Path:
    content = textwrap.dedent(f'''\
        import os
        from google.adk.agents import Agent

        MODEL = os.getenv("MODEL_ID", "gemini-2.0-flash")

        INSTRUCTION = """{instruction}"""

        agent = Agent(model=MODEL, name="test_agent", description="test",
                      instruction=INSTRUCTION, tools=[])
    ''')
    p = tmp_path / "test_agent.py"
    p.write_text(content, encoding="utf-8")
    return p


def test_patch_instruction_replaces_content(tmp_path):
    p = _make_agent_file(tmp_path, "original instruction")
    et.patch_instruction(str(p), "new improved instruction")
    content = p.read_text()
    assert "new improved instruction" in content
    assert "original instruction" not in content


def test_patch_instruction_preserves_surrounding_code(tmp_path):
    p = _make_agent_file(tmp_path, "original")
    et.patch_instruction(str(p), "updated")
    content = p.read_text()
    assert "import os" in content
    assert "from google.adk.agents import Agent" in content
    assert 'model=MODEL' in content


def test_patch_instruction_file_not_found():
    with pytest.raises(FileNotFoundError):
        et.patch_instruction("/nonexistent/path/agent.py", "new instruction")


def test_patch_instruction_no_instruction_block(tmp_path):
    p = tmp_path / "no_block.py"
    p.write_text("# no INSTRUCTION block here\nx = 1\n")
    with pytest.raises(ValueError, match="No INSTRUCTION"):
        et.patch_instruction(str(p), "something")


def test_patch_instruction_multiline(tmp_path):
    p = _make_agent_file(tmp_path, "line one\nline two\nline three")
    new_text = "step 1\nstep 2\nstep 3\nstep 4"
    et.patch_instruction(str(p), new_text)
    content = p.read_text()
    assert "step 1" in content
    assert "step 4" in content
    assert "line one" not in content


def test_patch_instruction_atomic_on_error(tmp_path):
    """If an error occurs, original file must be unchanged."""
    p = _make_agent_file(tmp_path, "original safe content")
    original = p.read_text()
    # No INSTRUCTION block in a dummy file — patch should raise
    bad_file = tmp_path / "bad.py"
    bad_file.write_text("# no block\n")
    with pytest.raises(ValueError):
        et.patch_instruction(str(bad_file), "new")
    # original file untouched
    assert p.read_text() == original


def test_patch_instruction_no_temp_files_left(tmp_path):
    p = _make_agent_file(tmp_path, "original")
    et.patch_instruction(str(p), "updated")
    tmp_files = list(tmp_path.glob("*.tmp"))
    assert tmp_files == []


# ── async wrappers smoke tests ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_patch_instruction_async(tmp_path):
    p = _make_agent_file(tmp_path, "original async test")
    await et.patch_instruction_async(str(p), "async updated instruction")
    content = p.read_text()
    assert "async updated instruction" in content


@pytest.mark.asyncio
async def test_get_current_instruction_none_when_empty():
    result = await et.get_current_instruction("nonexistent_agent")
    assert result is None


@pytest.mark.asyncio
async def test_get_current_instruction_returns_active():
    await edb.snapshot_instruction("my_agent", 1, "my instruction text", None, None, None)
    result = await et.get_current_instruction("my_agent")
    assert result == "my instruction text"


@pytest.mark.asyncio
async def test_release_stale_locks_returns_int():
    count = await et.release_stale_locks()
    assert isinstance(count, int)


@pytest.mark.asyncio
async def test_enqueue_and_dequeue_roundtrip():
    await et.enqueue_agent("roundtrip_agent", 3.0, [{"score": 3.0}])
    await edb.mark_queue_entry_done("roundtrip_agent", "high")
    entry = await et.dequeue_next_agent()
    assert entry is not None
    assert entry["agent_name"] == "roundtrip_agent"


@pytest.mark.asyncio
async def test_log_and_get_unprocessed():
    await et.log_evolution_event("log_agent", "reflection_score", 2.5, "bad")
    events = await et.get_unprocessed_events()
    assert any(e["agent_name"] == "log_agent" for e in events)


@pytest.mark.asyncio
async def test_mark_event_processed_async():
    await et.log_evolution_event("proc_agent", "batch_review", 3.0)
    events = await et.get_unprocessed_events()
    eid = events[0]["id"]
    ok = await et.mark_event_processed(eid)
    assert ok is True
    again = await et.mark_event_processed(eid)
    assert again is False
