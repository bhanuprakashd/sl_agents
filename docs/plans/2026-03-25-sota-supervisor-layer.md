# SOTA Autonomous Supervisor Layer — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a pure-Python supervisor layer to `aass_agents` that gives every agent invocation an audit trail, loop detection, circuit breaking, checkpoint/resume, and staleness-aware caching — with zero changes to any `agents/*.py` file.

**Architecture:** A `Supervisor` class in `tools/supervisor.py` wires five components (EventLog, PipelineRun, LoopGuard, CircuitBreaker, StalenessRegistry) into two ADK callbacks (`before_agent_callback` / `after_agent_callback`) attached to `company_orchestrator` in `main.py`. All state is persisted to `sales_memory.db` via five new tables. No LLM calls are added.

**Tech Stack:** Python 3.11+, SQLite (via stdlib `sqlite3`), `asyncio.to_thread`, SHA-256 (`hashlib`), Google ADK `>=0.5.0` callback API, `pytest` + `unittest.mock` for tests.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `tools/supervisor_db.py` | Create | Schema DDL + async CRUD helpers for all 5 supervisor tables |
| `tools/supervisor.py` | Create | `Supervisor` class + all 5 components; callback functions |
| `tools/supervisor_tools.py` | Create | ADK-compatible read-only tools: `list_dlq`, `get_run_status` |
| `tests/test_supervisor.py` | Create | Unit tests for all components (time-mock, event-injection) |
| `shared/memory_store.py` | Modify | Call `init_supervisor_tables()` on import |
| `main.py` | Modify | Attach supervisor callbacks; add `reset-circuit` + `resume` CLI commands |

---

## Task 1: supervisor_db.py — Schema & Async Helpers

**Files:**
- Create: `tools/supervisor_db.py`
- Test: `tests/test_supervisor.py`

- [ ] **Step 1: Write failing schema test**

```python
# tests/test_supervisor.py
import sqlite3, pytest
from pathlib import Path
from tools.supervisor_db import init_supervisor_tables, SUPERVISOR_DB_PATH

def test_init_creates_all_tables(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    monkeypatch.setattr("tools.supervisor_db.SUPERVISOR_DB_PATH", db)
    init_supervisor_tables()
    conn = sqlite3.connect(db)
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    assert tables >= {
        "supervisor_runs", "supervisor_events",
        "supervisor_circuit_breakers", "supervisor_dlq",
        "supervisor_output_validity"
    }
    conn.close()
```

- [ ] **Step 2: Run test — verify FAIL**
```bash
cd aass_agents && python -m pytest tests/test_supervisor.py::test_init_creates_all_tables -v
```
Expected: `ModuleNotFoundError` or `ImportError`

- [ ] **Step 3: Create `tools/supervisor_db.py`**

```python
"""
Supervisor DB — schema init and async CRUD helpers for all 5 supervisor tables.
All writes use asyncio.to_thread to avoid blocking the event loop (matches memory_store.py).
SQLite opened in WAL mode for safe concurrent access.
"""
import sqlite3
import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

SUPERVISOR_DB_PATH = Path(__file__).parent.parent / "sales_memory.db"

AGENT_TTL_DAYS: dict[str, Optional[float]] = {
    "lead_researcher": 7,
    "outreach_composer": 14,
    "sales_call_prep": 3,
    "objection_handler": None,      # per-run — never cache
    "proposal_generator": 30,
    "crm_updater": None,
    "deal_analyst": 1,
    "audience_builder": 7,
    "campaign_composer": 14,
    "content_strategist": 14,
    "seo_analyst": 30,
    "campaign_analyst": 7,
    "brand_voice": 90,
    "pm_agent": None,
    "architect_agent": float("inf"),  # manual reset only
    "devops_agent": None,
    "db_agent": None,
    "backend_builder_agent": None,
    "frontend_builder_agent": None,
    "qa_agent": None,
    "reflection_agent": None,       # meta-agent, never cached
    "company_orchestrator": None,   # router, never cached
    "_default": 7,                  # safety net for unlisted agents
}


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(SUPERVISOR_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_supervisor_tables() -> None:
    """Create supervisor tables if they don't exist. Safe to call multiple times."""
    with _get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS supervisor_runs (
                run_id          TEXT PRIMARY KEY,
                pipeline_type   TEXT NOT NULL,
                status          TEXT NOT NULL DEFAULT 'pending',
                current_step    INT DEFAULT 0,
                total_steps     INT,
                context_json    TEXT,
                checkpoint_json TEXT,
                created_at      TEXT NOT NULL,
                updated_at      TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS supervisor_events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id      TEXT NOT NULL,
                agent_name  TEXT NOT NULL,
                event_type  TEXT NOT NULL,
                payload_json TEXT,
                created_at  TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_sup_events_run
                ON supervisor_events(run_id);
            CREATE INDEX IF NOT EXISTS idx_sup_events_agent
                ON supervisor_events(agent_name, created_at);

            CREATE TABLE IF NOT EXISTS supervisor_circuit_breakers (
                agent_name      TEXT PRIMARY KEY,
                failure_count   INT NOT NULL DEFAULT 0,
                last_failure_at TEXT,
                opened_at       TEXT,
                state           TEXT NOT NULL DEFAULT 'closed'
            );

            CREATE TABLE IF NOT EXISTS supervisor_dlq (
                run_id               TEXT PRIMARY KEY,
                pipeline_type        TEXT,
                blocked_on           TEXT,
                last_error           TEXT,
                completed_steps_json TEXT,
                created_at           TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS supervisor_output_validity (
                entity_id   TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                agent_name  TEXT NOT NULL,
                run_id      TEXT,
                last_run_at TEXT,
                invalidated_by TEXT,
                expires_at  TEXT,
                PRIMARY KEY (entity_id, entity_type, agent_name)
            );
        """)


# ── Runs ─────────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.utcnow().isoformat()


def create_run(run_id: str, pipeline_type: str, context: dict) -> None:
    with _get_conn() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO supervisor_runs
               (run_id, pipeline_type, status, current_step, context_json, created_at, updated_at)
               VALUES (?, ?, 'pending', 0, ?, ?, ?)""",
            (run_id, pipeline_type, json.dumps(context), _now(), _now()),
        )


def update_run(run_id: str, **kwargs) -> None:
    """Update any column on supervisor_runs by name."""
    kwargs["updated_at"] = _now()
    cols = ", ".join(f"{k} = ?" for k in kwargs)
    vals = list(kwargs.values()) + [run_id]
    with _get_conn() as conn:
        conn.execute(f"UPDATE supervisor_runs SET {cols} WHERE run_id = ?", vals)


def get_run(run_id: str) -> Optional[dict]:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM supervisor_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        return dict(row) if row else None


# ── Events ───────────────────────────────────────────────────────────────────

def append_event(run_id: str, agent_name: str, event_type: str, payload: dict) -> None:
    with _get_conn() as conn:
        conn.execute(
            """INSERT INTO supervisor_events (run_id, agent_name, event_type, payload_json, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (run_id, agent_name, event_type, json.dumps(payload), _now()),
        )


def get_recent_events(run_id: str, limit: int = 10) -> list[dict]:
    with _get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM supervisor_events WHERE run_id = ?
               ORDER BY id DESC LIMIT ?""",
            (run_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]


# ── Circuit Breakers ──────────────────────────────────────────────────────────

def get_circuit(agent_name: str) -> dict:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM supervisor_circuit_breakers WHERE agent_name = ?",
            (agent_name,),
        ).fetchone()
        if row:
            return dict(row)
        return {"agent_name": agent_name, "failure_count": 0, "state": "closed",
                "last_failure_at": None, "opened_at": None}


def upsert_circuit(agent_name: str, **kwargs) -> None:
    existing = get_circuit(agent_name)
    existing.update(kwargs)
    with _get_conn() as conn:
        conn.execute(
            """INSERT INTO supervisor_circuit_breakers
               (agent_name, failure_count, last_failure_at, opened_at, state)
               VALUES (:agent_name, :failure_count, :last_failure_at, :opened_at, :state)
               ON CONFLICT(agent_name) DO UPDATE SET
                   failure_count   = excluded.failure_count,
                   last_failure_at = excluded.last_failure_at,
                   opened_at       = excluded.opened_at,
                   state           = excluded.state""",
            existing,
        )


# ── DLQ ──────────────────────────────────────────────────────────────────────

def push_dlq(run_id: str, pipeline_type: str, blocked_on: str,
             last_error: str, completed_steps: list) -> None:
    with _get_conn() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO supervisor_dlq
               (run_id, pipeline_type, blocked_on, last_error, completed_steps_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (run_id, pipeline_type, blocked_on, last_error,
             json.dumps(completed_steps), _now()),
        )


def list_dlq_entries() -> list[dict]:
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM supervisor_dlq ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


# ── Output Validity ───────────────────────────────────────────────────────────

def set_validity(entity_id: str, entity_type: str, agent_name: str,
                 run_id: str, ttl_days: Optional[float]) -> None:
    now = datetime.utcnow()
    if ttl_days is None:
        expires_at = None          # per-run — always stale
    elif ttl_days == float("inf"):
        expires_at = "9999-12-31"  # architect: manual reset only
    else:
        expires_at = (now + timedelta(days=ttl_days)).isoformat()

    with _get_conn() as conn:
        conn.execute(
            """INSERT INTO supervisor_output_validity
               (entity_id, entity_type, agent_name, run_id, last_run_at, expires_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(entity_id, entity_type, agent_name) DO UPDATE SET
                   run_id      = excluded.run_id,
                   last_run_at = excluded.last_run_at,
                   expires_at  = excluded.expires_at,
                   invalidated_by = NULL""",
            (entity_id, entity_type, agent_name, run_id, now.isoformat(), expires_at),
        )


def is_stale(entity_id: str, entity_type: str, agent_name: str) -> bool:
    """Return True if no valid cached output exists for this agent + entity."""
    with _get_conn() as conn:
        row = conn.execute(
            """SELECT expires_at, invalidated_by FROM supervisor_output_validity
               WHERE entity_id=? AND entity_type=? AND agent_name=?""",
            (entity_id, entity_type, agent_name),
        ).fetchone()

    if not row:
        return True  # never run
    if row["invalidated_by"]:
        return True  # explicitly invalidated
    if row["expires_at"] is None:
        return True  # per-run agent
    if row["expires_at"] == "9999-12-31":
        return False  # architect: never expires
    return datetime.utcnow().isoformat() > row["expires_at"]


def invalidate(entity_id: str, entity_type: str, agent_names: list[str],
               reason: str) -> None:
    with _get_conn() as conn:
        for name in agent_names:
            conn.execute(
                """UPDATE supervisor_output_validity
                   SET invalidated_by = ?
                   WHERE entity_id=? AND entity_type=? AND agent_name=?""",
                (reason, entity_id, entity_type, name),
            )
```

- [ ] **Step 4: Run test — verify PASS**
```bash
python -m pytest tests/test_supervisor.py::test_init_creates_all_tables -v
```

- [ ] **Step 5: Commit**
```bash
git add tools/supervisor_db.py tests/test_supervisor.py
git commit -m "feat: add supervisor_db schema and async CRUD helpers"
```

---

## Task 2: EventLog tests

**Files:**
- Modify: `tests/test_supervisor.py`

- [ ] **Step 1: Add EventLog tests**

```python
# append to tests/test_supervisor.py
import tools.supervisor_db as db

@pytest.fixture
def sdb(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.supervisor_db.SUPERVISOR_DB_PATH", tmp_path / "test.db")
    db.init_supervisor_tables()
    return db

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
```

- [ ] **Step 2: Run — verify PASS**
```bash
python -m pytest tests/test_supervisor.py -k "event" -v
```

- [ ] **Step 3: Commit**
```bash
git add tests/test_supervisor.py
git commit -m "test: add EventLog unit tests"
```

---

## Task 3: PipelineRun — state machine tests + implementation

**Files:**
- Modify: `tests/test_supervisor.py`
- Create: `tools/supervisor.py` (PipelineRun section)

- [ ] **Step 1: Write failing PipelineRun tests**

```python
# append to tests/test_supervisor.py
from tools.supervisor import PipelineRun

def test_pipeline_run_creates_and_transitions(sdb):
    pr = PipelineRun(db=sdb)
    run_id = pr.start("sales", {"company": "Acme"})
    assert run_id is not None
    row = sdb.get_run(run_id)
    assert row["status"] == "pending"
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
```

- [ ] **Step 2: Run — verify FAIL**
```bash
python -m pytest tests/test_supervisor.py -k "pipeline_run" -v
```
Expected: `ImportError: cannot import name 'PipelineRun'`

- [ ] **Step 3: Create `tools/supervisor.py` with PipelineRun**

```python
"""
Supervisor — wires EventLog, PipelineRun, LoopGuard, CircuitBreaker,
StalenessRegistry, and DeadLetterQueue into ADK callbacks.
"""
import hashlib
import json
import uuid
from datetime import datetime, timedelta
from typing import Optional

import tools.supervisor_db as _db


# ── PipelineRun ───────────────────────────────────────────────────────────────

class PipelineRun:
    def __init__(self, db=_db):
        self._db = db

    def start(self, pipeline_type: str, context: dict) -> str:
        run_id = str(uuid.uuid4())
        self._db.create_run(run_id, pipeline_type, context)
        self._db.update_run(run_id, status="running")
        return run_id

    def mark_step_done(self, run_id: str, step: int, checkpoint: dict) -> None:
        self._db.update_run(
            run_id,
            current_step=step,
            checkpoint_json=json.dumps(checkpoint),
        )

    def complete(self, run_id: str) -> None:
        self._db.update_run(run_id, status="completed")

    def fail(self, run_id: str, error: str) -> None:
        self._db.update_run(run_id, status="failed")
        row = self._db.get_run(run_id)
        if row:
            self._db.append_event(run_id, "_supervisor", "run.failed",
                                  {"error": error})

    def block(self, run_id: str) -> None:
        self._db.update_run(run_id, status="blocked")

    def get_checkpoint(self, run_id: str) -> Optional[dict]:
        row = self._db.get_run(run_id)
        if row and row.get("checkpoint_json"):
            return json.loads(row["checkpoint_json"])
        return None
```

- [ ] **Step 4: Run — verify PASS**
```bash
python -m pytest tests/test_supervisor.py -k "pipeline_run" -v
```

- [ ] **Step 5: Commit**
```bash
git add tools/supervisor.py tests/test_supervisor.py
git commit -m "feat: add PipelineRun state machine"
```

---

## Task 4: LoopGuard

**Files:**
- Modify: `tools/supervisor.py`
- Modify: `tests/test_supervisor.py`

- [ ] **Step 1: Write failing LoopGuard tests**

```python
# append to tests/test_supervisor.py
from tools.supervisor import LoopGuard

def test_loop_guard_no_loop(sdb):
    lg = LoopGuard(db=sdb)
    sdb.create_run("r1", "sales", {})
    # Different agents — no loop
    for agent in ["lead_researcher", "outreach_composer", "sales_call_prep"]:
        sdb.append_event("r1", agent, "agent.called", {"input_hash": "abc"})
    result = lg.check("r1", "deal_analyst", "xyz")
    assert result is None  # no block

def test_loop_guard_detects_exact_loop(sdb):
    lg = LoopGuard(db=sdb)
    sdb.create_run("r2", "sales", {})
    # Same agent, same hash 3 times
    for _ in range(3):
        sdb.append_event("r2", "lead_researcher", "agent.called",
                         {"input_hash": "deadbeef"})
    result = lg.check("r2", "lead_researcher", "original input text")
    assert result is not None
    assert "Loop" in result

def test_loop_guard_detects_thrash_loop(sdb):
    lg = LoopGuard(db=sdb)
    sdb.create_run("r3", "sales", {})
    # Same agent, 5 times, different inputs
    for i in range(5):
        sdb.append_event("r3", "lead_researcher", "agent.called",
                         {"input_hash": f"hash{i}"})
    result = lg.check("r3", "lead_researcher", "new different input")
    assert result is not None
    assert "thrash" in result.lower() or "loop" in result.lower()
```

- [ ] **Step 2: Run — verify FAIL**
```bash
python -m pytest tests/test_supervisor.py -k "loop_guard" -v
```

- [ ] **Step 3: Add LoopGuard to `tools/supervisor.py`**

```python
# ── LoopGuard ─────────────────────────────────────────────────────────────────

EXACT_LOOP_THRESHOLD = 3   # same agent + same hash
THRASH_LOOP_THRESHOLD = 5  # same agent regardless of hash
WINDOW_SIZE = 10


def _compute_input_hash(text: str) -> str:
    """SHA-256 of input text with run-specific fields stripped."""
    import re
    # strip UUIDs, ISO timestamps, session ids
    cleaned = re.sub(
        r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|'
        r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?',
        '',
        text,
        flags=re.IGNORECASE,
    )
    return hashlib.sha256(cleaned.encode()).hexdigest()[:16]


class LoopGuard:
    def __init__(self, db=_db):
        self._db = db

    def check(self, run_id: str, agent_name: str, input_text: str) -> Optional[str]:
        """
        Check for loops before an agent call.
        Returns a HITL message string if a loop is detected, None otherwise.
        """
        events = self._db.get_recent_events(run_id, limit=WINDOW_SIZE)
        called_events = [e for e in events if e["event_type"] == "agent.called"]

        input_hash = _compute_input_hash(input_text)

        # Exact loop: same agent + same hash N times
        same_hash_count = sum(
            1 for e in called_events
            if e["agent_name"] == agent_name
            and json.loads(e.get("payload_json") or "{}").get("input_hash") == input_hash
        )
        if same_hash_count >= EXACT_LOOP_THRESHOLD:
            return (
                f"⚠ Loop: {agent_name} called {same_hash_count}x with identical input. "
                f"Try a different approach or skip this step?"
            )

        # Thrash loop: same agent called too many times regardless of input
        same_agent_count = sum(
            1 for e in called_events if e["agent_name"] == agent_name
        )
        if same_agent_count >= THRASH_LOOP_THRESHOLD:
            return (
                f"⚠ Thrash detected: {agent_name} called {same_agent_count}x in this run. "
                f"Routing to reflection_agent for diagnosis."
            )

        return None

    def record(self, run_id: str, agent_name: str, input_text: str) -> str:
        """Record a new agent.called event. Returns the input_hash."""
        h = _compute_input_hash(input_text)
        self._db.append_event(run_id, agent_name, "agent.called",
                              {"input_hash": h, "input_excerpt": input_text[:200]})
        return h
```

- [ ] **Step 4: Run — verify PASS**
```bash
python -m pytest tests/test_supervisor.py -k "loop_guard" -v
```

- [ ] **Step 5: Commit**
```bash
git add tools/supervisor.py tests/test_supervisor.py
git commit -m "feat: add LoopGuard with exact and thrash loop detection"
```

---

## Task 5: CircuitBreaker

**Files:**
- Modify: `tools/supervisor.py`
- Modify: `tests/test_supervisor.py`

- [ ] **Step 1: Write failing CircuitBreaker tests**

```python
# append to tests/test_supervisor.py
from tools.supervisor import CircuitBreaker
from unittest.mock import patch
from datetime import datetime, timedelta

def test_circuit_breaker_opens_after_3_failures(sdb):
    cb = CircuitBreaker(db=sdb)
    for _ in range(3):
        cb.record_failure("lead_researcher")
    state = sdb.get_circuit("lead_researcher")["state"]
    assert state == "open"

def test_circuit_breaker_closed_allows_calls(sdb):
    cb = CircuitBreaker(db=sdb)
    assert cb.check("outreach_composer") is None  # no block

def test_circuit_breaker_open_blocks_calls(sdb):
    cb = CircuitBreaker(db=sdb)
    cb.record_failure("lead_researcher")
    cb.record_failure("lead_researcher")
    cb.record_failure("lead_researcher")
    result = cb.check("lead_researcher")
    assert result is not None
    assert "failed 3x" in result or "failed" in result

def test_circuit_breaker_auto_resets_after_30_min(sdb):
    cb = CircuitBreaker(db=sdb)
    for _ in range(3):
        cb.record_failure("deal_analyst")
    # Simulate 31 minutes passing
    past = (datetime.utcnow() - timedelta(minutes=31)).isoformat()
    sdb.upsert_circuit("deal_analyst", opened_at=past, state="open")
    result = cb.check("deal_analyst")
    assert result is None  # half-open: allow probe
    assert sdb.get_circuit("deal_analyst")["state"] == "half-open"

def test_circuit_breaker_resets_on_success(sdb):
    cb = CircuitBreaker(db=sdb)
    cb.record_failure("seo_analyst")
    cb.record_failure("seo_analyst")
    cb.record_failure("seo_analyst")
    cb.record_success("seo_analyst")
    state = sdb.get_circuit("seo_analyst")["state"]
    assert state == "closed"
```

- [ ] **Step 2: Run — verify FAIL**
```bash
python -m pytest tests/test_supervisor.py -k "circuit_breaker" -v
```

- [ ] **Step 3: Add CircuitBreaker to `tools/supervisor.py`**

```python
# ── CircuitBreaker ────────────────────────────────────────────────────────────

CIRCUIT_FAILURE_THRESHOLD = 3
CIRCUIT_RESET_MINUTES = 30


class CircuitBreaker:
    def __init__(self, db=_db):
        self._db = db

    def check(self, agent_name: str) -> Optional[str]:
        """
        Returns HITL message if circuit is open, None if call should proceed.
        Transitions open → half-open after 30 minutes.
        """
        circuit = self._db.get_circuit(agent_name)
        state = circuit["state"]

        if state == "closed":
            return None

        if state == "open":
            opened_at = circuit.get("opened_at")
            if opened_at:
                elapsed = datetime.utcnow() - datetime.fromisoformat(opened_at)
                if elapsed >= timedelta(minutes=CIRCUIT_RESET_MINUTES):
                    self._db.upsert_circuit(agent_name, state="half-open")
                    return None  # allow probe call
            return (
                f"⚠ {agent_name} failed {circuit['failure_count']}x. "
                f"Last error recorded. Fix the issue or skip this step? "
                f"Reset with: python main.py reset-circuit {agent_name}"
            )

        if state == "half-open":
            return None  # allow probe

        return None

    def record_failure(self, agent_name: str) -> None:
        circuit = self._db.get_circuit(agent_name)
        new_count = circuit["failure_count"] + 1
        new_state = "open" if new_count >= CIRCUIT_FAILURE_THRESHOLD else circuit["state"]
        opened_at = datetime.utcnow().isoformat() if new_state == "open" and circuit["state"] != "open" else circuit.get("opened_at")
        self._db.upsert_circuit(
            agent_name,
            failure_count=new_count,
            last_failure_at=datetime.utcnow().isoformat(),
            opened_at=opened_at,
            state=new_state,
        )

    def record_success(self, agent_name: str) -> None:
        self._db.upsert_circuit(
            agent_name,
            failure_count=0,
            state="closed",
            opened_at=None,
            last_failure_at=None,
        )

    @staticmethod
    def reset(agent_name: str) -> None:
        """CLI-only manual reset."""
        _db.upsert_circuit(agent_name, failure_count=0, state="closed",
                           opened_at=None, last_failure_at=None)
```

- [ ] **Step 4: Run — verify PASS**
```bash
python -m pytest tests/test_supervisor.py -k "circuit_breaker" -v
```

- [ ] **Step 5: Commit**
```bash
git add tools/supervisor.py tests/test_supervisor.py
git commit -m "feat: add CircuitBreaker with auto-reset and manual CLI reset"
```

---

## Task 6: StalenessRegistry

**Files:**
- Modify: `tools/supervisor.py`
- Modify: `tests/test_supervisor.py`

- [ ] **Step 1: Write failing StalenessRegistry tests**

```python
# append to tests/test_supervisor.py
from tools.supervisor import StalenessRegistry
from unittest.mock import patch
from datetime import datetime, timedelta

def test_staleness_new_agent_is_stale(sdb):
    sr = StalenessRegistry(db=sdb)
    # Never run before = stale
    assert sr.is_stale("Acme", "company", "lead_researcher") is True

def test_staleness_fresh_output_not_stale(sdb):
    sr = StalenessRegistry(db=sdb)
    sr.record_run("Acme", "company", "lead_researcher", "run-1")
    assert sr.is_stale("Acme", "company", "lead_researcher") is False

def test_staleness_expired_by_ttl(sdb):
    sr = StalenessRegistry(db=sdb)
    sr.record_run("Acme", "company", "lead_researcher", "run-1")
    # Fake expiry: set expires_at to the past
    past = (datetime.utcnow() - timedelta(days=1)).isoformat()
    sdb.invalidate("acme", "company", ["lead_researcher"], "ttl")
    assert sr.is_stale("Acme", "company", "lead_researcher") is True

def test_staleness_per_run_always_stale(sdb):
    sr = StalenessRegistry(db=sdb)
    sr.record_run("Acme", "company", "crm_updater", "run-1")
    # crm_updater TTL is None = always stale
    assert sr.is_stale("Acme", "company", "crm_updater") is True

def test_staleness_event_invalidation(sdb):
    sr = StalenessRegistry(db=sdb)
    sr.record_run("Acme", "company", "proposal_generator", "run-1")
    assert sr.is_stale("Acme", "company", "proposal_generator") is False
    sr.fire_event("Acme", "company", "deal_stage_change")
    assert sr.is_stale("Acme", "company", "proposal_generator") is True
```

- [ ] **Step 2: Run — verify FAIL**
```bash
python -m pytest tests/test_supervisor.py -k "staleness" -v
```

- [ ] **Step 3: Add StalenessRegistry to `tools/supervisor.py`**

```python
# ── StalenessRegistry ─────────────────────────────────────────────────────────

# Events that invalidate specific agent outputs
EVENT_INVALIDATION_MAP: dict[str, list[str]] = {
    "new_call_note":               ["sales_call_prep", "crm_updater"],
    "deal_stage_change":           ["proposal_generator", "deal_analyst"],
    "new_product_version":         ["proposal_generator", "qa_agent"],
    "win_loss_recorded":           ["audience_builder", "campaign_composer"],
    "new_company_news":            ["lead_researcher"],
    "campaign_performance_update": ["campaign_analyst", "campaign_composer"],
}


class StalenessRegistry:
    def __init__(self, db=_db):
        self._db = db

    def is_stale(self, entity_id: str, entity_type: str, agent_name: str) -> bool:
        return self._db.is_stale(entity_id.lower().strip(), entity_type, agent_name)

    def record_run(self, entity_id: str, entity_type: str,
                   agent_name: str, run_id: str) -> None:
        ttl = _db.AGENT_TTL_DAYS.get(agent_name, _db.AGENT_TTL_DAYS["_default"])
        self._db.set_validity(
            entity_id.lower().strip(), entity_type, agent_name, run_id, ttl
        )

    def fire_event(self, entity_id: str, entity_type: str, event_name: str) -> None:
        """Invalidate all agent outputs affected by this event."""
        affected = EVENT_INVALIDATION_MAP.get(event_name, [])
        if affected:
            self._db.invalidate(
                entity_id.lower().strip(), entity_type, affected,
                f"event:{event_name}"
            )
```

- [ ] **Step 4: Run — verify PASS**
```bash
python -m pytest tests/test_supervisor.py -k "staleness" -v
```

- [ ] **Step 5: Commit**
```bash
git add tools/supervisor.py tests/test_supervisor.py
git commit -m "feat: add StalenessRegistry with TTL and event invalidation"
```

---

## Task 7: DeadLetterQueue

**Files:**
- Modify: `tools/supervisor.py`
- Modify: `tests/test_supervisor.py`

- [ ] **Step 1: Write failing DLQ tests**

```python
# append to tests/test_supervisor.py
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
```

- [ ] **Step 2: Run — verify FAIL**
```bash
python -m pytest tests/test_supervisor.py -k "dlq" -v
```

- [ ] **Step 3: Add DeadLetterQueue to `tools/supervisor.py`**

```python
# ── DeadLetterQueue ───────────────────────────────────────────────────────────

class DeadLetterQueue:
    def __init__(self, db=_db):
        self._db = db

    def push(self, run_id: str, pipeline_type: str, blocked_on: str,
             last_error: str, completed_steps: list) -> str:
        self._db.push_dlq(run_id, pipeline_type, blocked_on, last_error, completed_steps)
        return (
            f"⚠ Run {run_id} blocked after all retries on {blocked_on}. "
            f"Completed: {', '.join(completed_steps) or 'none'}. "
            f"Last error: {last_error}. "
            f"Resume when ready: python main.py resume {run_id}"
        )

    def list_entries(self) -> list[dict]:
        return self._db.list_dlq_entries()
```

- [ ] **Step 4: Run — verify PASS**
```bash
python -m pytest tests/test_supervisor.py -k "dlq" -v
```

- [ ] **Step 5: Commit**
```bash
git add tools/supervisor.py tests/test_supervisor.py
git commit -m "feat: add DeadLetterQueue with HITL message formatting"
```

---

## Task 8: Supervisor — main class wiring all components

**Files:**
- Modify: `tools/supervisor.py`
- Modify: `tests/test_supervisor.py`

- [ ] **Step 1: Write failing Supervisor integration tests**

```python
# append to tests/test_supervisor.py
from tools.supervisor import Supervisor

def test_supervisor_pre_call_check_passes_clean(sdb):
    sup = Supervisor(db=sdb)
    run_id = sup.pipeline_run.start("sales", {"company": "Acme"})
    result = sup.pre_call_check(run_id, "lead_researcher", "research Acme Corp")
    assert result is None  # no block

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
```

- [ ] **Step 2: Run — verify FAIL**
```bash
python -m pytest tests/test_supervisor.py -k "supervisor_pre_call or supervisor_logs or supervisor_blocks or supervisor_update" -v
```

- [ ] **Step 3: Add Supervisor class to `tools/supervisor.py`**

```python
# ── Supervisor ────────────────────────────────────────────────────────────────

class Supervisor:
    """
    Wires all 5 supervisor components. Used by ADK callbacks in main.py.
    Thread-safe: all DB writes go through asyncio.to_thread in supervisor_db.
    """

    def __init__(self, db=_db):
        self.pipeline_run = PipelineRun(db=db)
        self.loop_guard = LoopGuard(db=db)
        self.circuit_breaker = CircuitBreaker(db=db)
        self.staleness = StalenessRegistry(db=db)
        self.dlq = DeadLetterQueue(db=db)
        self._db = db
        self._step_counters: dict[str, list[str]] = {}  # run_id -> [agent_names]

    def pre_call_check(self, run_id: Optional[str], agent_name: str,
                       input_text: str) -> Optional[str]:
        """
        Run all pre-call guards. Returns HITL message if blocked, None to proceed.
        Called from before_agent_callback in main.py.
        """
        if run_id is None:
            return None  # not inside a supervised run

        # Skip supervision of meta-agents
        if agent_name in ("reflection_agent", "company_orchestrator",
                          "sales_orchestrator", "marketing_orchestrator",
                          "product_orchestrator"):
            return None

        # 1. Circuit breaker
        circuit_msg = self.circuit_breaker.check(agent_name)
        if circuit_msg:
            self._db.append_event(run_id, agent_name, "circuit.opened",
                                  {"message": circuit_msg})
            return circuit_msg

        # 2. Loop guard
        loop_msg = self.loop_guard.check(run_id, agent_name, input_text)
        if loop_msg:
            self._db.append_event(run_id, agent_name, "loop.detected",
                                  {"message": loop_msg})
            return loop_msg

        return None

    def log_called(self, run_id: Optional[str], agent_name: str,
                   input_text: str) -> None:
        if not run_id:
            return
        self.loop_guard.record(run_id, agent_name, input_text)
        # Track step order for checkpointing
        if run_id not in self._step_counters:
            self._step_counters[run_id] = []
        self._step_counters[run_id].append(agent_name)

    def log_returned(self, run_id: Optional[str], agent_name: str,
                     output_text: str, duration_ms: int = 0,
                     error: Optional[str] = None) -> None:
        if not run_id:
            return
        if error:
            self.circuit_breaker.record_failure(agent_name)
        else:
            self.circuit_breaker.record_success(agent_name)
        self._db.append_event(run_id, agent_name, "agent.returned", {
            "output_excerpt": output_text[:500],
            "duration_ms": duration_ms,
            "error": error,
        })

    def checkpoint(self, run_id: Optional[str], agent_name: str) -> None:
        if not run_id:
            return
        steps = self._step_counters.get(run_id, [])
        step_num = len(steps)
        self.pipeline_run.mark_step_done(
            run_id, step_num,
            checkpoint={"last_agent": agent_name, "completed_steps": steps},
        )

    def update_validity(self, run_id: Optional[str], agent_name: str,
                        state: dict) -> None:
        """Record a fresh output for staleness tracking."""
        if not run_id:
            return
        entity_id = (state.get("entity_id") or state.get("company")
                     or state.get("campaign") or state.get("product_id") or "unknown")
        entity_type = state.get("entity_type", "company")
        self.staleness.record_run(entity_id, entity_type, agent_name, run_id)
```

- [ ] **Step 4: Run — verify PASS**
```bash
python -m pytest tests/test_supervisor.py -k "supervisor" -v
```

- [ ] **Step 5: Commit**
```bash
git add tools/supervisor.py tests/test_supervisor.py
git commit -m "feat: add Supervisor class wiring all 5 components"
```

---

## Task 9: supervisor_tools.py — Read-only ADK tools

**Files:**
- Create: `tools/supervisor_tools.py`
- Modify: `tests/test_supervisor.py`

- [ ] **Step 1: Write failing tool tests**

```python
# append to tests/test_supervisor.py
from tools.supervisor_tools import list_dlq, get_run_status

def test_list_dlq_returns_entries(sdb, monkeypatch):
    import tools.supervisor_db as mock_db
    monkeypatch.setattr("tools.supervisor_tools._db", sdb)
    sdb.push_dlq("run-10", "sales", "lead_researcher", "API down", ["pm_agent"])
    result = list_dlq()
    assert result["count"] == 1
    assert result["entries"][0]["blocked_on"] == "lead_researcher"

def test_get_run_status_found(sdb, monkeypatch):
    monkeypatch.setattr("tools.supervisor_tools._db", sdb)
    sdb.create_run("run-20", "marketing", {"campaign": "Q2"})
    result = get_run_status("run-20")
    assert result["found"] is True
    assert result["status"] == "pending"

def test_get_run_status_not_found(sdb, monkeypatch):
    monkeypatch.setattr("tools.supervisor_tools._db", sdb)
    result = get_run_status("nonexistent")
    assert result["found"] is False
```

- [ ] **Step 2: Run — verify FAIL**
```bash
python -m pytest tests/test_supervisor.py -k "list_dlq or get_run_status" -v
```

- [ ] **Step 3: Create `tools/supervisor_tools.py`**

```python
"""
Read-only ADK-compatible tools for supervisor observability.
These may be exposed to orchestrators. They do NOT modify supervisor state.
Control-plane operations (reset-circuit, resume) are CLI-only via main.py.
"""
import tools.supervisor_db as _db


def list_dlq() -> dict:
    """
    List all pipeline runs currently blocked in the dead letter queue.
    Read-only — does not modify supervisor state.

    Returns:
        dict with count and entries list, each entry having:
        run_id, pipeline_type, blocked_on, last_error, completed_steps, created_at
    """
    entries = _db.list_dlq_entries()
    # Parse completed_steps_json for each entry
    import json
    for e in entries:
        if e.get("completed_steps_json"):
            e["completed_steps"] = json.loads(e["completed_steps_json"])
        else:
            e["completed_steps"] = []
    return {"count": len(entries), "entries": entries}


def get_run_status(run_id: str) -> dict:
    """
    Get the current status of a pipeline run.
    Read-only — does not modify supervisor state.

    Args:
        run_id: The pipeline run UUID to look up.

    Returns:
        dict with found, run_id, pipeline_type, status, current_step, updated_at
        or found=False if not found.
    """
    row = _db.get_run(run_id)
    if not row:
        return {"found": False, "run_id": run_id}
    return {
        "found": True,
        "run_id": row["run_id"],
        "pipeline_type": row["pipeline_type"],
        "status": row["status"],
        "current_step": row["current_step"],
        "updated_at": row["updated_at"],
    }
```

- [ ] **Step 4: Run — verify PASS**
```bash
python -m pytest tests/test_supervisor.py -k "list_dlq or get_run_status" -v
```

- [ ] **Step 5: Commit**
```bash
git add tools/supervisor_tools.py tests/test_supervisor.py
git commit -m "feat: add read-only ADK supervisor tools (list_dlq, get_run_status)"
```

---

## Task 10: memory_store.py — init supervisor tables on startup

**Files:**
- Modify: `shared/memory_store.py`

- [ ] **Step 1: Write failing test**

```python
# append to tests/test_supervisor.py
def test_memory_store_inits_supervisor_tables(tmp_path, monkeypatch):
    """Importing memory_store should create supervisor tables in the same DB."""
    import importlib
    monkeypatch.setattr("tools.supervisor_db.SUPERVISOR_DB_PATH", tmp_path / "mem.db")
    monkeypatch.setattr("shared.memory_store.DB_PATH", tmp_path / "mem.db")
    # Re-import to trigger _init_db
    import shared.memory_store as ms
    importlib.reload(ms)
    import sqlite3
    conn = sqlite3.connect(tmp_path / "mem.db")
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    assert "supervisor_runs" in tables
    conn.close()
```

- [ ] **Step 2: Run — verify FAIL**
```bash
python -m pytest tests/test_supervisor.py::test_memory_store_inits_supervisor_tables -v
```

- [ ] **Step 3: Add init call to `shared/memory_store.py`**

At the end of `_init_db()`, add:
```python
# Initialise supervisor tables in the same DB
from tools.supervisor_db import init_supervisor_tables
init_supervisor_tables()
```

- [ ] **Step 4: Run — verify PASS**
```bash
python -m pytest tests/test_supervisor.py::test_memory_store_inits_supervisor_tables -v
```

- [ ] **Step 5: Run full test suite — no regressions**
```bash
python -m pytest tests/ -v
```
Expected: all tests pass

- [ ] **Step 6: Commit**
```bash
git add shared/memory_store.py
git commit -m "feat: init supervisor tables on memory_store startup"
```

---

## Task 11: main.py — attach callbacks + CLI commands

**Files:**
- Modify: `main.py`

- [ ] **Step 1: Add supervisor callbacks and CLI commands to `main.py`**

Replace the existing `main.py` content with:

```python
"""
Sales Agent Team — Google ADK Entry Point

Run modes:
  python main.py              # Interactive CLI session
  python main.py --web        # Launch ADK web UI
  python main.py reset-circuit <agent_name>   # Reset a tripped circuit breaker
  python main.py resume <run_id>              # Resume a DLQ-blocked pipeline run
  adk api_server main.py      # Start as API server
"""

import os
import sys
import asyncio
import uuid
from dotenv import load_dotenv

load_dotenv()

from agents.company_orchestrator_agent import company_orchestrator
from tools.supervisor import Supervisor
from tools.supervisor_db import init_supervisor_tables

# Initialise supervisor tables before any agent runs
init_supervisor_tables()

_supervisor = Supervisor()


# ── ADK Callbacks ─────────────────────────────────────────────────────────────

def _before_agent_callback(callback_context):
    """
    Runs BEFORE ADK dispatches any agent call in the tree.
    Returns Content to skip the agent (guard triggered); None to allow.
    """
    from google.genai.types import Content, Part

    run_id = callback_context.state.get("supervisor_run_id")
    agent_name = getattr(callback_context, "agent_name", "unknown")
    user_content = getattr(callback_context, "user_content", None)
    input_text = ""
    if user_content and hasattr(user_content, "parts") and user_content.parts:
        input_text = user_content.parts[0].text or ""

    block_msg = _supervisor.pre_call_check(run_id, agent_name, input_text)
    if block_msg:
        return Content(parts=[Part(text=block_msg)])

    _supervisor.log_called(run_id, agent_name, input_text)
    return None


def _after_agent_callback(callback_context, agent_response):
    """
    Runs AFTER ADK gets the agent's response.
    Used for logging, checkpointing, and validity updates.
    """
    run_id = callback_context.state.get("supervisor_run_id")
    agent_name = getattr(callback_context, "agent_name", "unknown")
    output_text = ""
    if agent_response and hasattr(agent_response, "parts") and agent_response.parts:
        output_text = agent_response.parts[0].text or ""

    _supervisor.log_returned(run_id, agent_name, output_text)
    _supervisor.checkpoint(run_id, agent_name)
    _supervisor.update_validity(run_id, agent_name, dict(callback_context.state))
    return None  # pass response through unchanged


# Attach callbacks to root agent — ADK propagates to all sub-agents
company_orchestrator.before_agent_callback = _before_agent_callback
company_orchestrator.after_agent_callback = _after_agent_callback

# Export root_agent for ADK CLI and web UI discovery
root_agent = company_orchestrator


def _generate_orgchart():
    try:
        from tools.generate_orgchart import run as orgchart_run
        orgchart_run(out="orgchart.html", open_browser=False)
    except Exception as exc:
        print(f"[OrgChart] Generation skipped: {exc}")


# ── CLI Session ───────────────────────────────────────────────────────────────

async def run_cli():
    """Run an interactive CLI session with the GTM orchestrator."""
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai.types import Content, Part

    session_service = InMemorySessionService()
    APP_NAME = "sales-agent-team"
    USER_ID = "rep-001"
    SESSION_ID = "session-001"

    await session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID,
    )

    runner = Runner(
        agent=company_orchestrator,
        app_name=APP_NAME,
        session_service=session_service,
    )

    _generate_orgchart()

    from shared.memory_store import DB_PATH
    print("\n" + "═" * 60)
    print("  Sales Agent Team — Powered by Google ADK")
    print("═" * 60)
    print("  Sales:     Research · Outreach · Call Prep · Objections · Proposals · CRM")
    print("  Marketing: Audience · Campaigns · Content · SEO · Analytics · Brand Voice")
    print("  Product:   PRD · Architecture · Infra · DB · Backend · Frontend · QA")
    print(f"  Memory:    {DB_PATH}")
    print("═" * 60)
    print("  Type 'quit' to exit\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        if user_input.lower() in ("quit", "exit", "q"):
            print("Session ended.")
            break
        if not user_input:
            continue

        # Create a new supervised run for each top-level request
        run_id = str(uuid.uuid4())
        pipeline_type = "sales"  # orchestrator will adjust; coarse default
        _supervisor.pipeline_run.start(pipeline_type, {"input": user_input})

        content = Content(role="user", parts=[Part(text=user_input)])

        print("\nGTM Team: ", end="", flush=True)
        try:
            async for event in runner.run_async(
                user_id=USER_ID,
                session_id=SESSION_ID,
                new_message=content,
            ):
                # Inject run_id into session state for callbacks
                if hasattr(event, "actions") and event.actions:
                    for action in event.actions:
                        if hasattr(action, "state_delta"):
                            action.state_delta["supervisor_run_id"] = run_id

                if event.is_final_response():
                    if event.content and event.content.parts:
                        print(event.content.parts[0].text)
                elif hasattr(event, "author") and event.author not in (
                    "company_orchestrator", "sales_orchestrator",
                    "marketing_orchestrator", "product_orchestrator",
                ):
                    print(f"\n[{event.author}] ", end="", flush=True)

            _supervisor.pipeline_run.complete(run_id)
        except Exception as exc:
            _supervisor.pipeline_run.fail(run_id, str(exc))
            print(f"\n⚠ Run failed: {exc}")
        print()


# ── CLI Commands ──────────────────────────────────────────────────────────────

def cmd_reset_circuit(agent_name: str) -> None:
    from tools.supervisor import CircuitBreaker
    CircuitBreaker.reset(agent_name)
    print(f"✓ Circuit breaker reset for: {agent_name}")


def cmd_resume(run_id: str) -> None:
    row = _supervisor._db.get_run(run_id)
    if not row:
        print(f"✗ Run not found: {run_id}")
        return
    import json
    checkpoint = json.loads(row["checkpoint_json"] or "{}")
    print(f"Run {run_id} | Status: {row['status']} | Step: {row['current_step']}")
    print(f"Checkpoint: {checkpoint}")
    print("Start a new session and reference this run_id to resume from this point.")


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--web" in args:
        import subprocess
        subprocess.run(["adk", "web"], cwd=os.path.dirname(os.path.abspath(__file__)))
    elif args and args[0] == "reset-circuit":
        if len(args) < 2:
            print("Usage: python main.py reset-circuit <agent_name>")
        else:
            cmd_reset_circuit(args[1])
    elif args and args[0] == "resume":
        if len(args) < 2:
            print("Usage: python main.py resume <run_id>")
        else:
            cmd_resume(args[1])
    else:
        asyncio.run(run_cli())
```

- [ ] **Step 2: Verify import works cleanly**
```bash
cd aass_agents && python -c "import main; print('✓ main.py imports OK')"
```
Expected: `✓ main.py imports OK` with no errors

- [ ] **Step 3: Run full test suite — all pass**
```bash
python -m pytest tests/ -v --tb=short
```
Expected: all tests pass

- [ ] **Step 4: Smoke-test CLI commands**
```bash
python main.py reset-circuit lead_researcher
# Expected: ✓ Circuit breaker reset for: lead_researcher

python main.py resume nonexistent-run-id
# Expected: ✗ Run not found: nonexistent-run-id
```

- [ ] **Step 5: Commit**
```bash
git add main.py
git commit -m "feat: attach supervisor callbacks to ADK runner and add CLI commands"
```

---

## Task 12: Coverage check + final verification

**Files:**
- No changes

- [ ] **Step 1: Run full test suite with coverage**
```bash
python -m pytest tests/test_supervisor.py -v --cov=tools/supervisor --cov=tools/supervisor_db --cov=tools/supervisor_tools --cov-report=term-missing
```
Expected: ≥80% coverage across all three supervisor modules

- [ ] **Step 2: Verify no agent files were modified**
```bash
git diff HEAD~11 -- agents/
```
Expected: empty diff (no agent files changed)

- [ ] **Step 3: Verify success criteria from spec**
```bash
# Tables exist
python -c "
import sqlite3; conn = sqlite3.connect('sales_memory.db')
tables = {r[0] for r in conn.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()}
required = {'supervisor_runs','supervisor_events','supervisor_circuit_breakers','supervisor_dlq','supervisor_output_validity'}
assert required <= tables, f'Missing: {required - tables}'
print('✓ All 5 supervisor tables present')
"

# Circuit breaker reset CLI works
python main.py reset-circuit qa_agent

# Smoke test DLQ listing
python -c "
from tools.supervisor_tools import list_dlq
result = list_dlq()
print(f'✓ list_dlq works, {result[\"count\"]} entries')
"
```

- [ ] **Step 4: Final commit**
```bash
git add .
git commit -m "feat: SOTA autonomous supervisor layer complete — event log, loop guard, circuit breaker, checkpoint/resume, staleness registry"
```

---

## Success Criteria Checklist

- [ ] Any pipeline can resume from last checkpoint (product: step N; sales/marketing: last completed agent)
- [ ] Every agent invocation produces `agent.called` + `agent.returned` events in `supervisor_events`
- [ ] Exact loops stopped before the 4th call with same input hash
- [ ] Stale outputs (TTL or event-triggered) automatically re-run without user intervention
- [ ] Failing agent opens circuit after 3 consecutive failures and is cleanly bypassed
- [ ] HITL triggered for exactly 4 blockers; all other paths autonomous
- [ ] `reset_circuit` only accessible via CLI — not exposed as ADK tool
- [ ] ≥80% test coverage; TTL tests use time-mock; event tests use injection helper
- [ ] Zero changes to any `agents/*.py` file
