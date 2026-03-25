"""
Smoke tests for the autoresearcher agent modules.

Verifies imports, agent names, sub-agent composition, and tool presence.
Never calls the live LLM.
"""
import pytest


# ── Import tests ──────────────────────────────────────────────────────────────

def test_evaluator_agent_imports():
    from agents.autoresearcher.evaluator_agent import evaluator_agent
    assert evaluator_agent.name == "evaluator_agent"


def test_hypothesis_agent_imports():
    from agents.autoresearcher.hypothesis_agent import hypothesis_agent
    assert hypothesis_agent.name == "hypothesis_agent"


def test_rewriter_agent_imports():
    from agents.autoresearcher.rewriter_agent import rewriter_agent
    assert rewriter_agent.name == "rewriter_agent"


def test_rollback_watchdog_agent_imports():
    from agents.autoresearcher.rollback_watchdog_agent import rollback_watchdog_agent
    assert rollback_watchdog_agent.name == "rollback_watchdog_agent"


def test_autoresearcher_orchestrator_imports():
    from agents.autoresearcher.autoresearcher_orchestrator_agent import autoresearcher_orchestrator
    assert autoresearcher_orchestrator.name == "autoresearcher_orchestrator"


# ── Sub-agent composition ─────────────────────────────────────────────────────

def test_autoresearcher_orchestrator_has_four_sub_agents():
    from agents.autoresearcher.autoresearcher_orchestrator_agent import autoresearcher_orchestrator
    names = {a.name for a in autoresearcher_orchestrator.sub_agents}
    assert "evaluator_agent" in names
    assert "hypothesis_agent" in names
    assert "rewriter_agent" in names
    assert "rollback_watchdog_agent" in names


def test_autoresearcher_orchestrator_has_reflection_agent():
    from agents.autoresearcher.autoresearcher_orchestrator_agent import autoresearcher_orchestrator
    names = {a.name for a in autoresearcher_orchestrator.sub_agents}
    assert "reflection_agent" in names


def test_evaluator_agent_has_reflection_sub_agent():
    from agents.autoresearcher.evaluator_agent import evaluator_agent
    names = {a.name for a in evaluator_agent.sub_agents}
    assert "reflection_agent" in names


# ── company_orchestrator wired up ─────────────────────────────────────────────

def test_company_orchestrator_includes_autoresearcher():
    from agents.company_orchestrator_agent import company_orchestrator
    names = {a.name for a in company_orchestrator.sub_agents}
    assert "autoresearcher_orchestrator" in names


def test_company_orchestrator_still_has_all_original_departments():
    from agents.company_orchestrator_agent import company_orchestrator
    names = {a.name for a in company_orchestrator.sub_agents}
    for expected in (
        "sales_orchestrator",
        "marketing_orchestrator",
        "product_orchestrator",
        "engineering_orchestrator",
        "research_orchestrator",
        "qa_orchestrator",
    ):
        assert expected in names, f"Missing: {expected}"


# ── Tool layer smoke tests (no DB calls, just import) ─────────────────────────

def test_evolution_db_imports():
    from tools import evolution_db
    assert hasattr(evolution_db, "log_evolution_event_sync")
    assert hasattr(evolution_db, "snapshot_instruction_sync")
    assert hasattr(evolution_db, "acquire_rewrite_lock_sync")
    assert hasattr(evolution_db, "InvalidStateTransition")


def test_evolution_tools_imports():
    from tools import evolution_tools
    assert hasattr(evolution_tools, "patch_instruction")
    assert hasattr(evolution_tools, "get_agent_file_path")
    assert hasattr(evolution_tools, "restore_instruction")
    assert hasattr(evolution_tools, "get_baseline_score")


# ── evolution_db functional (isolated) ───────────────────────────────────────

@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    import tools.evolution_db as edb
    db_path = tmp_path / "smoke_test.db"
    monkeypatch.setattr(edb, "EVOLUTION_DB_PATH", db_path)
    edb.init_db()
    yield edb


def test_full_evolution_cycle(isolated_db):
    """Smoke test: log event → enqueue → hypothesis → snapshot → lock → release."""
    edb = isolated_db

    # Log a low-score event
    edb.log_evolution_event_sync("smoke_agent", "reflection_score", 3.5, "bad output")
    events = edb.get_unprocessed_events_sync()
    assert len(events) == 1

    # Mark processed
    assert edb.mark_event_processed_sync(events[0]["id"]) is True
    assert edb.get_unprocessed_events_sync() == []

    # Enqueue agent for improvement
    edb.enqueue_agent_sync("smoke_agent", 3.5, [{"score": 3.5, "output_sample": "bad"}])
    pending = edb.get_queue_pending_sync()
    assert len(pending) == 1

    # Save hypothesis
    version = edb.get_next_version_sync("smoke_agent")
    hid = edb.save_hypothesis_sync("smoke_agent", version, "root cause", "new INSTRUCTION", "high")
    assert hid > 0

    # Mark queue done
    edb.mark_queue_entry_done_sync("smoke_agent", "high")
    entry = edb.dequeue_next_agent_sync()
    assert entry["agent_name"] == "smoke_agent"

    # Acquire lock
    assert edb.acquire_rewrite_lock_sync("smoke_agent", version) is True
    assert edb.acquire_rewrite_lock_sync("smoke_agent", version) is False

    # Snapshot instruction
    edb.snapshot_instruction_sync("smoke_agent", version, "new INSTRUCTION", 3.5, "2026-03-25T00:00:00+00:00", hid)
    assert edb.get_current_instruction_sync("smoke_agent") == "new INSTRUCTION"

    # Release lock
    edb.release_rewrite_lock_sync("smoke_agent")
    assert edb.acquire_rewrite_lock_sync("smoke_agent", version + 1) is True

    # Mark stable
    edb.update_version_status_sync("smoke_agent", version, "stable")
    history = edb.get_evolution_history_sync("smoke_agent")
    assert history[0]["status"] == "stable"
    assert edb.get_consecutive_stable_count_sync("smoke_agent") == 1
