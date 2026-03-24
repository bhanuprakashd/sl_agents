# tests/test_supervisor.py
import sqlite3, pytest
from datetime import datetime, timedelta
from pathlib import Path
from tools.supervisor_db import init_supervisor_tables, SUPERVISOR_DB_PATH
import tools.supervisor_db as db


def test_init_creates_all_tables(tmp_path, monkeypatch):
    d = tmp_path / "test.db"
    monkeypatch.setattr("tools.supervisor_db.SUPERVISOR_DB_PATH", d)
    init_supervisor_tables()
    conn = sqlite3.connect(d)
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    assert tables >= {
        "supervisor_runs", "supervisor_events",
        "supervisor_circuit_breakers", "supervisor_dlq",
        "supervisor_output_validity"
    }
    conn.close()


# ── shared fixture ────────────────────────────────────────────────────────────

@pytest.fixture
def sdb(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.supervisor_db.SUPERVISOR_DB_PATH", tmp_path / "test.db")
    db.init_supervisor_tables()
    return db


# ── Task 2: EventLog tests ────────────────────────────────────────────────────

def test_append_and_retrieve_events(sdb):
    sdb.create_run("run-1", "sales", {"company": "Acme"})
    sdb.append_event("run-1", "lead_researcher", "agent.called", {"input_hash": "abc123"})
    sdb.append_event("run-1", "lead_researcher", "agent.returned", {"duration_ms": 1200})
    events = sdb.get_recent_events("run-1", limit=10)
    assert len(events) == 2
    assert events[0]["event_type"] == "agent.returned"  # most recent first
    assert events[1]["event_type"] == "agent.called"


def test_events_scoped_to_run_id(sdb):
    sdb.create_run("run-A", "sales", {})
    sdb.create_run("run-B", "sales", {})
    sdb.append_event("run-A", "lead_researcher", "agent.called", {})
    sdb.append_event("run-B", "outreach_composer", "agent.called", {})
    assert len(sdb.get_recent_events("run-A")) == 1
    assert len(sdb.get_recent_events("run-B")) == 1


# ── Task 3: PipelineRun tests ─────────────────────────────────────────────────

from tools.supervisor import PipelineRun


def test_pipeline_run_creates_and_transitions(sdb):
    pr = PipelineRun(db=sdb)
    run_id = pr.start("sales", {"company": "Acme"})
    assert run_id is not None
    row = sdb.get_run(run_id)
    assert row["status"] == "running"
    assert row["pipeline_type"] == "sales"


def test_pipeline_run_checkpoint_and_resume(sdb):
    pr = PipelineRun(db=sdb)
    run_id = pr.start("product", {"product_id": "p-123"})
    pr.mark_step_done(run_id, step=3, checkpoint={"product_id": "p-123", "product_step": 3})
    row = sdb.get_run(run_id)
    assert row["current_step"] == 3
    import json
    cp = json.loads(row["checkpoint_json"])
    assert cp["product_step"] == 3


def test_pipeline_run_complete(sdb):
    pr = PipelineRun(db=sdb)
    run_id = pr.start("marketing", {})
    pr.complete(run_id)
    assert sdb.get_run(run_id)["status"] == "completed"


def test_pipeline_run_fail(sdb):
    pr = PipelineRun(db=sdb)
    run_id = pr.start("sales", {})
    pr.fail(run_id, "Something broke")
    row = sdb.get_run(run_id)
    assert row["status"] == "failed"


# ── Task 4: LoopGuard tests ───────────────────────────────────────────────────

from tools.supervisor import LoopGuard


def test_loop_guard_no_loop(sdb):
    lg = LoopGuard(db=sdb)
    sdb.create_run("r1", "sales", {})
    for agent in ["lead_researcher", "outreach_composer", "sales_call_prep"]:
        sdb.append_event("r1", agent, "agent.called", {"input_hash": "abc"})
    result = lg.check("r1", "deal_analyst", "xyz")
    assert result is None


def test_loop_guard_detects_exact_loop(sdb):
    lg = LoopGuard(db=sdb)
    sdb.create_run("r2", "sales", {})
    for _ in range(3):
        sdb.append_event("r2", "lead_researcher", "agent.called",
                         {"input_hash": "deadbeef"})
    result = lg.check("r2", "lead_researcher", "original input text")
    assert result is not None
    assert "Loop" in result


def test_loop_guard_detects_thrash_loop(sdb):
    lg = LoopGuard(db=sdb)
    sdb.create_run("r3", "sales", {})
    for i in range(5):
        sdb.append_event("r3", "lead_researcher", "agent.called",
                         {"input_hash": f"hash{i}"})
    result = lg.check("r3", "lead_researcher", "new different input")
    assert result is not None
    assert "thrash" in result.lower() or "loop" in result.lower()


# ── Task 5: CircuitBreaker tests ──────────────────────────────────────────────

from tools.supervisor import CircuitBreaker
from unittest.mock import patch


def test_circuit_breaker_opens_after_3_failures(sdb):
    cb = CircuitBreaker(db=sdb)
    for _ in range(3):
        cb.record_failure("lead_researcher")
    state = sdb.get_circuit("lead_researcher")["state"]
    assert state == "open"


def test_circuit_breaker_closed_allows_calls(sdb):
    cb = CircuitBreaker(db=sdb)
    assert cb.check("outreach_composer") is None


def test_circuit_breaker_open_blocks_calls(sdb):
    cb = CircuitBreaker(db=sdb)
    cb.record_failure("lead_researcher")
    cb.record_failure("lead_researcher")
    cb.record_failure("lead_researcher")
    result = cb.check("lead_researcher")
    assert result is not None
    assert "failed" in result


def test_circuit_breaker_auto_resets_after_30_min(sdb):
    cb = CircuitBreaker(db=sdb)
    for _ in range(3):
        cb.record_failure("deal_analyst")
    past = (datetime.utcnow() - timedelta(minutes=31)).isoformat()
    sdb.upsert_circuit("deal_analyst", opened_at=past, state="open")
    result = cb.check("deal_analyst")
    assert result is None
    assert sdb.get_circuit("deal_analyst")["state"] == "half-open"


def test_circuit_breaker_resets_on_success(sdb):
    cb = CircuitBreaker(db=sdb)
    cb.record_failure("seo_analyst")
    cb.record_failure("seo_analyst")
    cb.record_failure("seo_analyst")
    cb.record_success("seo_analyst")
    state = sdb.get_circuit("seo_analyst")["state"]
    assert state == "closed"


# ── Task 6: StalenessRegistry tests ──────────────────────────────────────────

from tools.supervisor import StalenessRegistry


def test_staleness_new_agent_is_stale(sdb):
    sr = StalenessRegistry(db=sdb)
    assert sr.is_stale("Acme", "company", "lead_researcher") is True


def test_staleness_fresh_output_not_stale(sdb):
    sr = StalenessRegistry(db=sdb)
    sr.record_run("Acme", "company", "lead_researcher", "run-1")
    assert sr.is_stale("Acme", "company", "lead_researcher") is False


def test_staleness_per_run_always_stale(sdb):
    sr = StalenessRegistry(db=sdb)
    sr.record_run("Acme", "company", "crm_updater", "run-1")
    assert sr.is_stale("Acme", "company", "crm_updater") is True


def test_staleness_event_invalidation(sdb):
    sr = StalenessRegistry(db=sdb)
    sr.record_run("Acme", "company", "proposal_generator", "run-1")
    assert sr.is_stale("Acme", "company", "proposal_generator") is False
    sr.fire_event("Acme", "company", "deal_stage_change")
    assert sr.is_stale("Acme", "company", "proposal_generator") is True


# ── Task 7: DeadLetterQueue tests ─────────────────────────────────────────────

from tools.supervisor import DeadLetterQueue


def test_dlq_push_and_list(sdb):
    dlq = DeadLetterQueue(db=sdb)
    dlq.push("run-99", "product", "devops_agent", "Railway billing failed",
              completed_steps=["pm_agent", "architect_agent"])
    entries = dlq.list_entries()
    assert len(entries) == 1
    assert entries[0]["blocked_on"] == "devops_agent"
    assert entries[0]["run_id"] == "run-99"


def test_dlq_message_format(sdb):
    dlq = DeadLetterQueue(db=sdb)
    msg = dlq.push("run-88", "sales", "lead_researcher", "API rate limit",
                   completed_steps=[])
    assert "run-88" in msg
    assert "lead_researcher" in msg
    assert "python main.py resume" in msg


# ── Task 8: Supervisor main class tests ──────────────────────────────────────

from tools.supervisor import Supervisor


def test_supervisor_pre_call_check_passes_clean(sdb):
    sup = Supervisor(db=sdb)
    run_id = sup.pipeline_run.start("sales", {"company": "Acme"})
    result = sup.pre_call_check(run_id, "lead_researcher", "research Acme Corp")
    assert result is None


def test_supervisor_logs_called_and_returned(sdb):
    sup = Supervisor(db=sdb)
    run_id = sup.pipeline_run.start("sales", {"company": "Acme"})
    sup.log_called(run_id, "lead_researcher", "research Acme")
    sup.log_returned(run_id, "lead_researcher", "Profile: Acme Corp...", duration_ms=800)
    events = sdb.get_recent_events(run_id)
    types = [e["event_type"] for e in events]
    assert "agent.called" in types
    assert "agent.returned" in types


def test_supervisor_pre_call_blocks_open_circuit(sdb):
    sup = Supervisor(db=sdb)
    run_id = sup.pipeline_run.start("sales", {})
    for _ in range(3):
        sup.circuit_breaker.record_failure("lead_researcher")
    result = sup.pre_call_check(run_id, "lead_researcher", "research Acme")
    assert result is not None
    assert "failed" in result


def test_supervisor_update_validity(sdb):
    sup = Supervisor(db=sdb)
    run_id = sup.pipeline_run.start("sales", {"company": "Acme"})
    sup.update_validity(run_id, "lead_researcher", {"entity_id": "acme", "entity_type": "company"})
    assert sup.staleness.is_stale("acme", "company", "lead_researcher") is False
