"""
Unit tests for tools/evolution_db.py

Uses an in-memory SQLite DB (via monkeypatching EVOLUTION_DB_PATH) so tests
never touch the real evolution.db file.
"""
import pytest
import asyncio
import tempfile
from pathlib import Path

import tools.evolution_db as edb


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Point evolution_db at a fresh temp file for each test."""
    db_path = tmp_path / "test_evolution.db"
    monkeypatch.setattr(edb, "EVOLUTION_DB_PATH", db_path)
    edb.init_db()
    yield


# ── init ──────────────────────────────────────────────────────────────────────

def test_init_db_creates_tables(tmp_path, monkeypatch):
    db_path = tmp_path / "fresh.db"
    monkeypatch.setattr(edb, "EVOLUTION_DB_PATH", db_path)
    edb.init_db()
    assert db_path.exists()
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    conn.close()
    for table in ("agent_versions", "evolution_events", "hypotheses", "evaluator_queue", "rewrite_locks"):
        assert table in tables


# ── evolution_events ──────────────────────────────────────────────────────────

def test_log_and_get_unprocessed():
    edb.log_evolution_event_sync("sales_agent", "reflection_score", 4.5, "bad output")
    edb.log_evolution_event_sync("sales_agent", "reflection_score", 3.0, "another bad one")
    events = edb.get_unprocessed_events_sync()
    assert len(events) == 2
    assert all(e["processed"] == 0 for e in events)
    assert all(e["agent_name"] == "sales_agent" for e in events)


def test_output_sample_truncated():
    long_sample = "x" * 3000
    edb.log_evolution_event_sync("foo_agent", "batch_review", 5.0, long_sample)
    events = edb.get_unprocessed_events_sync()
    assert len(events[0]["output_sample"]) == 2000


def test_mark_event_processed_compare_and_swap():
    edb.log_evolution_event_sync("bar_agent", "manual", 2.0)
    events = edb.get_unprocessed_events_sync()
    event_id = events[0]["id"]

    first = edb.mark_event_processed_sync(event_id)
    second = edb.mark_event_processed_sync(event_id)

    assert first is True
    assert second is False  # already processed


def test_get_unprocessed_excludes_processed():
    edb.log_evolution_event_sync("baz_agent", "reflection_score", 5.0, "sample")
    events = edb.get_unprocessed_events_sync()
    edb.mark_event_processed_sync(events[0]["id"])
    assert edb.get_unprocessed_events_sync() == []


def test_get_post_rewrite_scores():
    import time
    t0 = edb._now_iso()
    edb.log_evolution_event_sync("agent_x", "reflection_score", 7.0)
    edb.log_evolution_event_sync("agent_x", "reflection_score", 8.0)
    scores = edb.get_post_rewrite_scores_sync("agent_x", after_timestamp=t0, n=10)
    assert scores == [7.0, 8.0]


def test_get_baseline_score_raises_if_no_events():
    with pytest.raises(ValueError, match="No evolution events"):
        edb.get_baseline_score_sync("unknown_agent")


def test_get_baseline_score_mean():
    edb.log_evolution_event_sync("agent_y", "reflection_score", 4.0)
    edb.log_evolution_event_sync("agent_y", "reflection_score", 6.0)
    mean, ts = edb.get_baseline_score_sync("agent_y", last_n=10)
    assert mean == pytest.approx(5.0)
    assert ts  # non-empty timestamp


# ── agent_versions ────────────────────────────────────────────────────────────

def test_snapshot_and_get_current_instruction():
    assert edb.get_current_instruction_sync("my_agent") is None
    edb.snapshot_instruction_sync("my_agent", 1, "INSTRUCTION v1", None, None, None)
    assert edb.get_current_instruction_sync("my_agent") == "INSTRUCTION v1"


def test_get_next_version_starts_at_1():
    assert edb.get_next_version_sync("brand_new_agent") == 1


def test_get_next_version_increments():
    edb.snapshot_instruction_sync("versioned_agent", 1, "v1", None, None, None)
    assert edb.get_next_version_sync("versioned_agent") == 2


def test_update_version_status_valid_transition():
    edb.snapshot_instruction_sync("status_agent", 1, "v1", 5.0, "2026-01-01T00:00:00+00:00", None)
    edb.update_version_status_sync("status_agent", 1, "stable")
    history = edb.get_evolution_history_sync("status_agent")
    assert history[0]["status"] == "stable"


def test_update_version_status_invalid_transition_raises():
    edb.snapshot_instruction_sync("bad_agent", 1, "v1", None, None, None)
    edb.update_version_status_sync("bad_agent", 1, "rolled_back")
    # rolled_back → anything is invalid
    with pytest.raises(edb.InvalidStateTransition):
        edb.update_version_status_sync("bad_agent", 1, "stable")


def test_get_consecutive_stable_count():
    edb.snapshot_instruction_sync("stable_agent", 1, "v1", None, None, None)
    edb.update_version_status_sync("stable_agent", 1, "stable")
    edb.snapshot_instruction_sync("stable_agent", 2, "v2", None, None, None)
    edb.update_version_status_sync("stable_agent", 2, "stable")
    assert edb.get_consecutive_stable_count_sync("stable_agent") == 2


def test_get_consecutive_stable_count_broken_by_rollback():
    edb.snapshot_instruction_sync("rollback_agent", 1, "v1", None, None, None)
    edb.update_version_status_sync("rollback_agent", 1, "stable")
    edb.snapshot_instruction_sync("rollback_agent", 2, "v2", None, None, None)
    edb.update_version_status_sync("rollback_agent", 2, "rolled_back")
    edb.snapshot_instruction_sync("rollback_agent", 3, "v3", None, None, None)
    edb.update_version_status_sync("rollback_agent", 3, "stable")
    # v3 is stable, v2 is rolled_back → streak breaks at v2 → count = 1
    assert edb.get_consecutive_stable_count_sync("rollback_agent") == 1


def test_get_rewrite_count_last_24h():
    edb.snapshot_instruction_sync("rate_agent", 1, "v1", None, None, None)
    edb.snapshot_instruction_sync("rate_agent", 2, "v2", None, None, None)
    count = edb.get_rewrite_count_last_24h_sync("rate_agent")
    assert count == 2


# ── hypotheses ────────────────────────────────────────────────────────────────

def test_save_hypothesis_returns_id():
    hid = edb.save_hypothesis_sync(
        "hyp_agent", 1, "root cause here", "new INSTRUCTION", "high"
    )
    assert isinstance(hid, int)
    assert hid > 0


# ── evaluator_queue ───────────────────────────────────────────────────────────

def test_enqueue_and_get_pending():
    edb.enqueue_agent_sync("q_agent", 3.5, [{"score": 3.5}])
    pending = edb.get_queue_pending_sync()
    assert len(pending) == 1
    assert pending[0]["agent_name"] == "q_agent"


def test_enqueue_upserts_lower_priority():
    edb.enqueue_agent_sync("dup_agent", 5.0, [])
    edb.enqueue_agent_sync("dup_agent", 3.0, [{"score": 3.0}])  # worse score → update
    pending = edb.get_queue_pending_sync()
    assert len(pending) == 1
    assert pending[0]["priority"] == pytest.approx(3.0)


def test_enqueue_does_not_update_if_new_priority_is_better():
    edb.enqueue_agent_sync("keep_agent", 3.0, [])
    edb.enqueue_agent_sync("keep_agent", 5.0, [])  # better score — no update
    pending = edb.get_queue_pending_sync()
    assert pending[0]["priority"] == pytest.approx(3.0)


def test_mark_queue_entry_done_and_dequeue():
    edb.enqueue_agent_sync("done_agent", 2.0, [{"score": 2.0}])
    edb.mark_queue_entry_done_sync("done_agent", "high")
    entry = edb.dequeue_next_agent_sync()
    assert entry is not None
    assert entry["agent_name"] == "done_agent"
    assert entry["confidence"] == "high"


def test_dequeue_prefers_high_confidence_over_medium():
    edb.enqueue_agent_sync("medium_agent", 1.0, [])
    edb.mark_queue_entry_done_sync("medium_agent", "medium")
    edb.enqueue_agent_sync("high_agent", 3.0, [])
    edb.mark_queue_entry_done_sync("high_agent", "high")
    entry = edb.dequeue_next_agent_sync()
    assert entry["agent_name"] == "high_agent"


def test_mark_queue_entry_aborted():
    edb.enqueue_agent_sync("abort_agent", 4.0, [])
    edb.mark_queue_entry_aborted_sync("abort_agent", "low confidence")
    pending = edb.get_queue_pending_sync()
    assert all(e["agent_name"] != "abort_agent" for e in pending)


# ── rewrite_locks ─────────────────────────────────────────────────────────────

def test_acquire_lock_returns_true():
    result = edb.acquire_rewrite_lock_sync("lock_agent", 1)
    assert result is True


def test_acquire_lock_second_attempt_returns_false():
    edb.acquire_rewrite_lock_sync("dupe_lock_agent", 1)
    result = edb.acquire_rewrite_lock_sync("dupe_lock_agent", 2)
    assert result is False


def test_release_lock_allows_reacquire():
    edb.acquire_rewrite_lock_sync("release_agent", 1)
    edb.release_rewrite_lock_sync("release_agent")
    result = edb.acquire_rewrite_lock_sync("release_agent", 2)
    assert result is True


def test_release_stale_locks():
    import sqlite3
    from datetime import datetime, timezone, timedelta
    # Insert a stale lock with expires_at in the past
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    conn = sqlite3.connect(str(edb.EVOLUTION_DB_PATH))
    conn.execute(
        "INSERT INTO rewrite_locks (agent_name, locked_at, expires_at, version) VALUES (?,?,?,?)",
        ("stale_agent", past, past, 1),
    )
    conn.commit()
    conn.close()
    released = edb.release_stale_locks_sync()
    assert released >= 1


# ── async wrappers smoke tests ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_async_log_and_get():
    await edb.log_evolution_event("async_agent", "reflection_score", 3.5, "sample")
    events = await edb.get_unprocessed_events()
    assert any(e["agent_name"] == "async_agent" for e in events)


@pytest.mark.asyncio
async def test_async_snapshot_and_get_instruction():
    await edb.snapshot_instruction("async_snap_agent", 1, "v1 text", None, None, None)
    result = await edb.get_current_instruction("async_snap_agent")
    assert result == "v1 text"
