# Autoresearcher Self-Evolving Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a self-evolving `autoresearcher` department that monitors agent outputs, rewrites underperforming agent instructions, and auto-rolls back if quality drops.

**Architecture:** Four specialist agents (evaluator → hypothesis → rewriter → watchdog) wired under `autoresearcher_orchestrator`. SQLite evolution DB stores versions, scores, locks, and a priority queue. Dynamic instruction loading via `get_current_instruction()` hot-reloads agent instructions without process restart.

**Tech Stack:** Python 3.11+, Google ADK (`google.adk.agents`), SQLite (WAL mode), `pytest`, existing `tools/supervisor_db.py` and `tools/memory_tools.py` patterns.

**Spec:** `docs/superpowers/specs/2026-03-25-autoresearcher-design.md`

**Working directory for all commands:** `aass_agents/`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `tools/evolution_db.py` | Create | SQLite schema init + CRUD for 5 tables |
| `tools/evolution_tools.py` | Create | Disk patching, scoring, locks, queue, path resolution |
| `agents/evaluator_agent.py` | Create | Quality Evaluator — monitors scores, enqueues underperformers |
| `agents/hypothesis_agent.py` | Create | Improvement Researcher — generates instruction rewrites |
| `agents/rewriter_agent.py` | Create | Instruction Engineer — patches .py files atomically |
| `agents/rollback_watchdog_agent.py` | Create | Stability Monitor — measures post-rewrite quality, rolls back |
| `agents/autoresearcher_orchestrator_agent.py` | Create | Department root — routes to 4 specialists |
| `agents/company_orchestrator_agent.py` | Modify | Add autoresearcher routing + sub_agent |
| `tools/supervisor.py` | Modify | Add task counter trigger + watchdog poll thread |
| `tests/test_evolution_db.py` | Create | Unit tests for schema + CRUD |
| `tests/test_evolution_tools.py` | Create | Unit + integration tests for tools |
| `tests/test_autoresearcher.py` | Create | Integration tests for full loop |

---

## Task 1: Evolution DB — Schema and CRUD

**Files:**
- Create: `tools/evolution_db.py`
- Create: `tests/test_evolution_db.py`

- [ ] **Step 1.1: Write the failing schema test**

```python
# tests/test_evolution_db.py
import sqlite3, pytest
from pathlib import Path
import tools.evolution_db as edb


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.evolution_db.EVOLUTION_DB_PATH", tmp_path / "evo.db")
    edb.init_evolution_tables()
    return edb


def test_init_creates_all_tables(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.evolution_db.EVOLUTION_DB_PATH", tmp_path / "evo.db")
    edb.init_evolution_tables()
    conn = sqlite3.connect(tmp_path / "evo.db")
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    assert tables >= {
        "agent_versions", "evolution_events", "hypotheses",
        "rewrite_locks", "evaluator_queue"
    }
    conn.close()
```

- [ ] **Step 1.2: Run to verify it fails**

```bash
pytest tests/test_evolution_db.py::test_init_creates_all_tables -v
```
Expected: `FAILED` — `ModuleNotFoundError: No module named 'tools.evolution_db'`

- [ ] **Step 1.3: Implement `tools/evolution_db.py`**

```python
"""
Evolution DB — schema init and CRUD for the autoresearcher self-evolving loop.
5 tables: agent_versions, evolution_events, hypotheses, rewrite_locks, evaluator_queue.
Follows supervisor_db.py pattern: WAL mode, synchronous CRUD, Path-based DB path.
"""
import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Optional


EVOLUTION_DB_PATH = Path(__file__).parent.parent / "evolution.db"


class InvalidStateTransition(Exception):
    """Raised when an illegal agent_versions status transition is attempted."""


# Valid state machine transitions
_VALID_TRANSITIONS = {
    ("pending_watch", "stable"),
    ("pending_watch", "rolled_back"),
    ("stable", "superseded"),
    ("superseded", "stable"),
}


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(EVOLUTION_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _now() -> str:
    return datetime.utcnow().isoformat()


def init_evolution_tables() -> None:
    """Create all evolution tables. Safe to call multiple times."""
    with _get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS agent_versions (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_name          TEXT NOT NULL,
                version             INTEGER NOT NULL,
                instruction_text    TEXT NOT NULL,
                score_baseline      REAL,
                baseline_sampled_at TEXT,
                status              TEXT NOT NULL DEFAULT 'pending_watch',
                hypothesis_id       INTEGER,
                created_at          TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS evolution_events (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_name    TEXT NOT NULL,
                trigger_type  TEXT NOT NULL,
                score         REAL NOT NULL,
                output_sample TEXT,
                processed     INTEGER NOT NULL DEFAULT 0,
                created_at    TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS hypotheses (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_name       TEXT NOT NULL,
                version          INTEGER NOT NULL,
                root_cause       TEXT NOT NULL,
                hypothesis_text  TEXT NOT NULL,
                confidence       TEXT NOT NULL,
                created_at       TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS rewrite_locks (
                agent_name  TEXT PRIMARY KEY,
                locked_at   TEXT NOT NULL,
                expires_at  TEXT NOT NULL,
                version     INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS evaluator_queue (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_name TEXT NOT NULL UNIQUE,
                priority   REAL NOT NULL,
                evidence   TEXT NOT NULL,
                confidence TEXT,
                queued_at  TEXT NOT NULL,
                status     TEXT NOT NULL DEFAULT 'pending'
            );

            CREATE INDEX IF NOT EXISTS idx_evo_events_agent
                ON evolution_events(agent_name, created_at);
            CREATE INDEX IF NOT EXISTS idx_agent_versions_agent
                ON agent_versions(agent_name, version);
        """)


# ── agent_versions ─────────────────────────────────────────────────────────────

def insert_version(agent_name: str, version: int, instruction_text: str,
                   score_baseline: Optional[float], baseline_sampled_at: Optional[str],
                   hypothesis_id: Optional[int]) -> int:
    """Insert a new version row. Returns the new row id."""
    with _get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO agent_versions
               (agent_name, version, instruction_text, score_baseline,
                baseline_sampled_at, status, hypothesis_id, created_at)
               VALUES (?, ?, ?, ?, ?, 'pending_watch', ?, ?)""",
            (agent_name, version, instruction_text, score_baseline,
             baseline_sampled_at, hypothesis_id, _now()),
        )
        return cur.lastrowid


def transition_version_status(agent_name: str, version: int, new_status: str) -> None:
    """Transition a version to a new status. Raises InvalidStateTransition on bad move."""
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT status FROM agent_versions WHERE agent_name=? AND version=?",
            (agent_name, version),
        ).fetchone()
        if not row:
            raise ValueError(f"No version {version} for agent {agent_name}")
        current = row["status"]
        if (current, new_status) not in _VALID_TRANSITIONS:
            raise InvalidStateTransition(
                f"{agent_name} v{version}: {current!r} → {new_status!r} is not allowed"
            )
        conn.execute(
            "UPDATE agent_versions SET status=? WHERE agent_name=? AND version=?",
            (new_status, agent_name, version),
        )


def get_current_instruction(agent_name: str) -> Optional[str]:
    """Return instruction_text for the most recent stable/pending_watch version, or None."""
    with _get_conn() as conn:
        row = conn.execute(
            """SELECT instruction_text FROM agent_versions
               WHERE agent_name=? AND status IN ('stable','pending_watch')
               ORDER BY version DESC LIMIT 1""",
            (agent_name,),
        ).fetchone()
        return row["instruction_text"] if row else None


def get_version_history(agent_name: str) -> list[dict]:
    """Return all versions for agent ordered by version ASC."""
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM agent_versions WHERE agent_name=? ORDER BY version ASC",
            (agent_name,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_pending_watch_entries() -> list[dict]:
    """Return all agent_versions rows with status='pending_watch'."""
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM agent_versions WHERE status='pending_watch'"
        ).fetchall()
        return [dict(r) for r in rows]


def get_latest_stable_before(agent_name: str, version: int) -> Optional[dict]:
    """Return the most recent stable/superseded row with version < given version."""
    with _get_conn() as conn:
        row = conn.execute(
            """SELECT * FROM agent_versions
               WHERE agent_name=? AND version<? AND status IN ('stable','superseded')
               ORDER BY version DESC LIMIT 1""",
            (agent_name, version),
        ).fetchone()
        return dict(row) if row else None


def get_consecutive_stable_count(agent_name: str) -> int:
    """Count most recent consecutive stable terminal-state versions (stable/rolled_back)."""
    with _get_conn() as conn:
        rows = conn.execute(
            """SELECT status FROM agent_versions
               WHERE agent_name=? AND status IN ('stable','rolled_back')
               ORDER BY version DESC""",
            (agent_name,),
        ).fetchall()
    count = 0
    for row in rows:
        if row["status"] == "stable":
            count += 1
        else:
            break
    return count


def supersede_prior_versions(agent_name: str, current_version: int) -> None:
    """Mark all stable versions with version < current_version as superseded."""
    with _get_conn() as conn:
        rows = conn.execute(
            """SELECT version FROM agent_versions
               WHERE agent_name=? AND version<? AND status='stable'""",
            (agent_name, current_version),
        ).fetchall()
    for row in rows:
        transition_version_status(agent_name, row["version"], "superseded")


# ── evolution_events ───────────────────────────────────────────────────────────

def insert_evolution_event(agent_name: str, trigger_type: str,
                           score: float, output_sample: Optional[str]) -> int:
    sample = (output_sample or "")[:2000]  # truncate to 2000 chars
    with _get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO evolution_events
               (agent_name, trigger_type, score, output_sample, processed, created_at)
               VALUES (?, ?, ?, ?, 0, ?)""",
            (agent_name, trigger_type, score, sample, _now()),
        )
        return cur.lastrowid


def mark_event_processed(event_id: int) -> bool:
    """Atomic CAS: set processed=1 only if currently 0. Returns True if this caller won."""
    with _get_conn() as conn:
        cur = conn.execute(
            "UPDATE evolution_events SET processed=1 WHERE id=? AND processed=0",
            (event_id,),
        )
        return cur.rowcount == 1


def get_unprocessed_events(agent_name: Optional[str] = None) -> list[dict]:
    with _get_conn() as conn:
        if agent_name:
            rows = conn.execute(
                "SELECT * FROM evolution_events WHERE processed=0 AND agent_name=? ORDER BY created_at",
                (agent_name,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM evolution_events WHERE processed=0 ORDER BY agent_name, created_at"
            ).fetchall()
        return [dict(r) for r in rows]


def get_recent_scores(agent_name: str, after_timestamp: Optional[str] = None,
                      last_n: int = 10) -> list[dict]:
    """Return up to last_n score events for agent, optionally filtered to after_timestamp."""
    with _get_conn() as conn:
        if after_timestamp:
            rows = conn.execute(
                """SELECT id, score, created_at FROM evolution_events
                   WHERE agent_name=? AND created_at>? ORDER BY created_at DESC LIMIT ?""",
                (agent_name, after_timestamp, last_n),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT id, score, created_at FROM evolution_events
                   WHERE agent_name=? ORDER BY created_at DESC LIMIT ?""",
                (agent_name, last_n),
            ).fetchall()
        return [dict(r) for r in rows]


# ── hypotheses ─────────────────────────────────────────────────────────────────

def insert_hypothesis(agent_name: str, version: int, root_cause: str,
                      hypothesis_text: str, confidence: str) -> int:
    with _get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO hypotheses
               (agent_name, version, root_cause, hypothesis_text, confidence, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (agent_name, version, root_cause, hypothesis_text, confidence, _now()),
        )
        return cur.lastrowid


# ── rewrite_locks ──────────────────────────────────────────────────────────────

def acquire_rewrite_lock(agent_name: str, version: int) -> bool:
    """Attempt to acquire lock. Returns True if acquired, False if already locked."""
    from datetime import timedelta
    locked_at = _now()
    expires_at = (datetime.utcnow() + timedelta(hours=72)).isoformat()
    with _get_conn() as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO rewrite_locks (agent_name, locked_at, expires_at, version) VALUES (?,?,?,?)",
            (agent_name, locked_at, expires_at, version),
        )
        return cur.rowcount == 1


def release_rewrite_lock(agent_name: str) -> None:
    with _get_conn() as conn:
        conn.execute("DELETE FROM rewrite_locks WHERE agent_name=?", (agent_name,))


def release_stale_locks() -> int:
    """Delete locks past expires_at. Returns count released."""
    now = _now()
    with _get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM rewrite_locks WHERE expires_at < ?", (now,)
        )
        return cur.rowcount


def is_locked(agent_name: str) -> bool:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT agent_name FROM rewrite_locks WHERE agent_name=?", (agent_name,)
        ).fetchone()
        return row is not None


# ── evaluator_queue ────────────────────────────────────────────────────────────

def enqueue_agent(agent_name: str, priority: float, evidence: list[dict]) -> None:
    """UPSERT: update priority/evidence if agent already queued with worse (higher) priority."""
    with _get_conn() as conn:
        conn.execute(
            """INSERT INTO evaluator_queue (agent_name, priority, evidence, queued_at, status)
               VALUES (?, ?, ?, ?, 'pending')
               ON CONFLICT(agent_name) DO UPDATE SET
                   priority  = CASE WHEN excluded.priority < priority THEN excluded.priority ELSE priority END,
                   evidence  = CASE WHEN excluded.priority < priority THEN excluded.evidence ELSE evidence END,
                   queued_at = CASE WHEN excluded.priority < priority THEN excluded.queued_at ELSE queued_at END""",
            (agent_name, priority, json.dumps(evidence), _now()),
        )


def dequeue_next_agent() -> Optional[dict]:
    """Return highest-priority pending or done entry ordered by confidence DESC, priority ASC."""
    with _get_conn() as conn:
        row = conn.execute(
            """SELECT * FROM evaluator_queue
               WHERE status IN ('pending','done')
               ORDER BY
                 CASE confidence WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END ASC,
                 priority ASC
               LIMIT 1""",
        ).fetchone()
        return dict(row) if row else None


def update_queue_status(agent_name: str, status: str,
                        confidence: Optional[str] = None) -> None:
    with _get_conn() as conn:
        if confidence is not None:
            conn.execute(
                "UPDATE evaluator_queue SET status=?, confidence=? WHERE agent_name=?",
                (status, confidence, agent_name),
            )
        else:
            conn.execute(
                "UPDATE evaluator_queue SET status=? WHERE agent_name=?",
                (status, agent_name),
            )


# ── rewrite count guards ───────────────────────────────────────────────────────

def get_rewrite_count(agent_name: str, hours: int) -> int:
    """Count rewrites (any status) for agent within the past N hours."""
    from datetime import timedelta
    since = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM agent_versions WHERE agent_name=? AND created_at>?",
            (agent_name, since),
        ).fetchone()
        return row[0]
```

- [ ] **Step 1.4: Run schema test to verify it passes**

```bash
pytest tests/test_evolution_db.py::test_init_creates_all_tables -v
```
Expected: `PASSED`

- [ ] **Step 1.5: Write remaining CRUD tests**

```python
# append to tests/test_evolution_db.py

def test_insert_and_get_version(db):
    vid = db.insert_version("test_agent", 0, "do stuff", 7.5, "2026-01-01T00:00:00", None)
    assert vid > 0
    history = db.get_version_history("test_agent")
    assert len(history) == 1
    assert history[0]["status"] == "pending_watch"
    assert history[0]["instruction_text"] == "do stuff"


def test_valid_status_transition(db):
    db.insert_version("test_agent", 0, "v0", None, None, None)
    db.transition_version_status("test_agent", 0, "stable")
    h = db.get_version_history("test_agent")
    assert h[0]["status"] == "stable"


def test_invalid_status_transition_raises(db):
    db.insert_version("test_agent", 0, "v0", None, None, None)
    db.transition_version_status("test_agent", 0, "rolled_back")
    with pytest.raises(db.InvalidStateTransition):
        db.transition_version_status("test_agent", 0, "stable")  # rolled_back is terminal


def test_get_current_instruction_returns_none_when_empty(db):
    assert db.get_current_instruction("nonexistent") is None


def test_get_current_instruction_returns_latest_active(db):
    db.insert_version("a", 0, "v0 text", None, None, None)
    db.transition_version_status("a", 0, "stable")
    db.insert_version("a", 1, "v1 text", None, None, None)
    # v1 is pending_watch — should be returned (most recent active)
    assert db.get_current_instruction("a") == "v1 text"


def test_mark_event_processed_cas(db):
    eid = db.insert_evolution_event("a", "reflection_score", 4.5, "bad output")
    assert db.mark_event_processed(eid) is True   # first caller wins
    assert db.mark_event_processed(eid) is False  # second caller loses


def test_rewrite_lock_unique(db):
    assert db.acquire_rewrite_lock("a", 1) is True
    assert db.acquire_rewrite_lock("a", 2) is False  # already locked


def test_release_stale_locks(db, monkeypatch):
    from datetime import timedelta
    # Insert a lock that expired 1 second ago
    past = (datetime.utcnow() - timedelta(seconds=1)).isoformat()
    conn = sqlite3.connect(db.EVOLUTION_DB_PATH)
    conn.execute("INSERT INTO rewrite_locks VALUES ('x', ?, ?, 1)", (past, past))
    conn.commit(); conn.close()
    released = db.release_stale_locks()
    assert released == 1


def test_enqueue_agent_upsert_keeps_better_priority(db):
    db.enqueue_agent("a", 5.0, [{"score": 5.0}])
    db.enqueue_agent("a", 3.0, [{"score": 3.0}])  # worse avg → higher priority → update
    db.enqueue_agent("a", 4.0, [{"score": 4.0}])  # not worse → no update
    row = db.dequeue_next_agent()
    assert row["priority"] == pytest.approx(3.0)


def test_dequeue_orders_by_confidence_then_priority(db):
    db.enqueue_agent("medium_agent", 2.0, [])
    db.update_queue_status("medium_agent", "done", "medium")
    db.enqueue_agent("high_agent", 4.0, [])
    db.update_queue_status("high_agent", "done", "high")
    first = db.dequeue_next_agent()
    assert first["agent_name"] == "high_agent"  # high confidence beats lower priority score


def test_get_consecutive_stable_count(db):
    db.insert_version("a", 0, "v0", None, None, None)
    db.transition_version_status("a", 0, "stable")
    db.insert_version("a", 1, "v1", None, None, None)
    db.transition_version_status("a", 1, "stable")
    db.insert_version("a", 2, "v2", None, None, None)
    db.transition_version_status("a", 2, "rolled_back")
    # Most recent terminal is rolled_back → streak = 0
    assert db.get_consecutive_stable_count("a") == 0


def test_get_rewrite_count_24h(db):
    db.insert_version("a", 0, "v0", None, None, None)
    db.insert_version("a", 1, "v1", None, None, None)
    assert db.get_rewrite_count("a", hours=24) == 2
```

- [ ] **Step 1.6: Run all evolution_db tests**

```bash
pytest tests/test_evolution_db.py -v
```
Expected: all PASSED

- [ ] **Step 1.7: Commit**

```bash
git add tools/evolution_db.py tests/test_evolution_db.py
git commit -m "feat: evolution_db schema and CRUD with tests"
```

---

## Task 2: Evolution Tools — Disk Ops, Scoring, Locks

**Files:**
- Create: `tools/evolution_tools.py`
- Create (extend): `tests/test_evolution_tools.py`

- [ ] **Step 2.1: Write failing unit tests for core tool functions**

```python
# tests/test_evolution_tools.py
import os, re, sqlite3, pytest
from pathlib import Path
import tools.evolution_db as edb
import tools.evolution_tools as et


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.evolution_db.EVOLUTION_DB_PATH", tmp_path / "evo.db")
    monkeypatch.setattr("tools.evolution_tools.EVOLUTION_DB_PATH", tmp_path / "evo.db")
    edb.init_evolution_tables()
    return edb


def test_get_agent_file_path_convention(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.evolution_tools.AGENTS_DIR", tmp_path)
    (tmp_path / "foo_agent.py").write_text("# agent")
    path = et.get_agent_file_path("foo_agent")
    assert path.endswith("foo_agent.py")


def test_get_agent_file_path_not_found(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.evolution_tools.AGENTS_DIR", tmp_path)
    with pytest.raises(FileNotFoundError):
        et.get_agent_file_path("nonexistent_agent")


def test_get_baseline_score_empty(db):
    score, ts = et.get_baseline_score("new_agent")
    assert score == 0.0


def test_get_baseline_score_partial(db):
    for s in [4.0, 5.0, 6.0]:
        edb.insert_evolution_event("a", "reflection_score", s, None)
    score, ts = et.get_baseline_score("a", last_n=10)
    assert score == pytest.approx(5.0)


def test_get_post_rewrite_scores_filters_by_timestamp(db):
    edb.insert_evolution_event("a", "reflection_score", 3.0, None)
    from datetime import datetime
    after_ts = datetime.utcnow().isoformat()
    edb.insert_evolution_event("a", "reflection_score", 8.0, None)
    scores = et.get_post_rewrite_scores("a", after_timestamp=after_ts, n=5)
    assert scores == pytest.approx([8.0])
```

- [ ] **Step 2.2: Run to verify they fail**

```bash
pytest tests/test_evolution_tools.py -v
```
Expected: `FAILED` — `ModuleNotFoundError`

- [ ] **Step 2.3: Implement `tools/evolution_tools.py`**

```python
"""
Evolution Tools — disk patching, scoring, locks, path resolution.
Used only by rewriter_agent and rollback_watchdog_agent.
All disk writes are atomic (temp file → os.rename).
"""
import os
import re
import compile as _compile_builtin
from pathlib import Path
from typing import Optional

import tools.evolution_db as edb
from tools.evolution_db import (
    insert_version, get_rewrite_count, acquire_rewrite_lock,
    release_rewrite_lock, release_stale_locks, insert_evolution_event,
    mark_event_processed, get_recent_scores, get_current_instruction,
)

AGENTS_DIR = str(Path(__file__).parent.parent / "agents")
EVOLUTION_DB_PATH = edb.EVOLUTION_DB_PATH  # re-exported for monkeypatching in tests


def get_agent_file_path(agent_name: str) -> str:
    """Resolve agent_name → agents/{agent_name}.py. Raises FileNotFoundError if absent."""
    path = Path(AGENTS_DIR) / f"{agent_name}.py"
    if not path.exists():
        raise FileNotFoundError(f"Agent file not found: {path}")
    return str(path)


def read_agent_instruction(agent_name: str) -> str:
    """Read INSTRUCTION_STATIC from the agent's .py file."""
    path = get_agent_file_path(agent_name)
    content = Path(path).read_text(encoding="utf-8")
    # Extract INSTRUCTION_STATIC = """...""" (triple-quoted)
    match = re.search(r'INSTRUCTION_STATIC\s*=\s*"""(.*?)"""', content, re.DOTALL)
    if match:
        return match.group(1)
    # Fallback: try INSTRUCTION = """..."""
    match = re.search(r'INSTRUCTION\s*=\s*"""(.*?)"""', content, re.DOTALL)
    if match:
        return match.group(1)
    raise ValueError(f"Could not find INSTRUCTION string in {path}")


def patch_instruction(agent_file_path: str, new_instruction: str) -> None:
    """Atomically replace INSTRUCTION_STATIC in .py file. Validates syntax first."""
    # Validate syntax
    try:
        compile(new_instruction, "<string>", "exec")
    except SyntaxError as e:
        raise SyntaxError(f"Invalid Python in proposed instruction: {e}") from e

    path = Path(agent_file_path)
    content = path.read_text(encoding="utf-8")

    # Replace INSTRUCTION_STATIC = """..."""
    new_content = re.sub(
        r'(INSTRUCTION_STATIC\s*=\s*""").*?(""")',
        lambda m: m.group(1) + new_instruction + m.group(2),
        content,
        count=1,
        flags=re.DOTALL,
    )
    if new_content == content:
        # Fallback: try bare INSTRUCTION
        new_content = re.sub(
            r'(INSTRUCTION\s*=\s*""").*?(""")',
            lambda m: m.group(1) + new_instruction + m.group(2),
            content,
            count=1,
            flags=re.DOTALL,
        )

    tmp_path = path.with_suffix(".py.tmp")
    tmp_path.write_text(new_content, encoding="utf-8")
    os.rename(str(tmp_path), str(path))  # atomic on POSIX


def snapshot_instruction(agent_name: str, version: int, instruction_text: str,
                         score_baseline: Optional[float],
                         baseline_sampled_at: Optional[str],
                         hypothesis_id: Optional[int]) -> int:
    """Save instruction snapshot to agent_versions DB. Returns row id."""
    return insert_version(
        agent_name, version, instruction_text,
        score_baseline, baseline_sampled_at, hypothesis_id,
    )


def restore_instruction(agent_name: str, target_version: int) -> None:
    """Restore a prior version from DB to disk + update DB statuses."""
    from tools.evolution_db import (
        get_version_history, transition_version_status,
        get_latest_stable_before, supersede_prior_versions,
    )
    history = get_version_history(agent_name)
    target = next((v for v in history if v["version"] == target_version), None)
    if target is None:
        raise ValueError(f"Version {target_version} not found for {agent_name}")
    path = get_agent_file_path(agent_name)
    patch_instruction(path, target["instruction_text"])
    # Update DB: target → stable
    transition_version_status(agent_name, target_version, "stable")


def get_baseline_score(agent_name: str, last_n: int = 10) -> tuple[float, str]:
    """Return (mean_score, sampled_at_iso) from last N evolution_events.
    Returns (0.0, now_iso) if no events found."""
    from datetime import datetime
    from tools.evolution_db import get_recent_scores as _get
    rows = _get(agent_name, last_n=last_n)
    now = datetime.utcnow().isoformat()
    if not rows:
        return (0.0, now)
    scores = [r["score"] for r in rows]
    return (sum(scores) / len(scores), now)


def get_post_rewrite_scores(agent_name: str, after_timestamp: str, n: int = 5) -> list[float]:
    """Return up to N scores from evolution_events created after after_timestamp."""
    rows = get_recent_scores(agent_name, after_timestamp=after_timestamp, last_n=n)
    return [r["score"] for r in rows]


def log_evolution_event(agent_name: str, trigger_type: str,
                        score: float, output_sample: Optional[str]) -> int:
    return insert_evolution_event(agent_name, trigger_type, score, output_sample)
```

- [ ] **Step 2.4: Run unit tests**

```bash
pytest tests/test_evolution_tools.py -v
```
Expected: all PASSED

- [ ] **Step 2.5: Write integration tests for disk patching (real files)**

```python
# append to tests/test_evolution_tools.py

AGENT_FIXTURE = '''\
"""Fixture agent."""
import os
from google.adk.agents import Agent
MODEL = os.getenv("MODEL_ID", "gemini-2.0-flash")
INSTRUCTION_STATIC = """You are a test agent. Do basic things."""
def get_instruction(agent_name):
    from tools.evolution_db import get_current_instruction
    dynamic = get_current_instruction(agent_name)
    return dynamic if dynamic is not None else INSTRUCTION_STATIC
test_fixture_agent = Agent(
    model=MODEL, name="test_fixture_agent",
    description="fixture", instruction=get_instruction("test_fixture_agent"), tools=[],
)
'''


def test_patch_instruction_modifies_file(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.evolution_tools.AGENTS_DIR", str(tmp_path))
    agent_file = tmp_path / "test_fixture_agent.py"
    agent_file.write_text(AGENT_FIXTURE)
    et.patch_instruction(str(agent_file), "New improved instruction.")
    content = agent_file.read_text()
    assert "New improved instruction." in content
    assert "Do basic things." not in content


def test_patch_instruction_does_not_corrupt_on_syntax_error(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.evolution_tools.AGENTS_DIR", str(tmp_path))
    agent_file = tmp_path / "test_fixture_agent.py"
    agent_file.write_text(AGENT_FIXTURE)
    original = agent_file.read_text()
    with pytest.raises(SyntaxError):
        et.patch_instruction(str(agent_file), "def broken(: invalid syntax")
    assert agent_file.read_text() == original  # original file unchanged


def test_snapshot_and_restore_roundtrip(tmp_path, monkeypatch, db):
    monkeypatch.setattr("tools.evolution_tools.AGENTS_DIR", str(tmp_path))
    agent_file = tmp_path / "my_agent.py"
    agent_file.write_text(AGENT_FIXTURE)
    # Snapshot version 0
    et.snapshot_instruction("my_agent", 0, "You are a test agent. Do basic things.", 7.0, None, None)
    edb.transition_version_status("my_agent", 0, "stable")
    # Patch to new instruction
    et.patch_instruction(str(agent_file), "Newer instruction content.")
    # Restore version 0
    et.restore_instruction("my_agent", 0)
    content = agent_file.read_text()
    assert "Do basic things." in content
```

- [ ] **Step 2.6: Run all evolution_tools tests**

```bash
pytest tests/test_evolution_tools.py -v
```
Expected: all PASSED

- [ ] **Step 2.7: Commit**

```bash
git add tools/evolution_tools.py tests/test_evolution_tools.py
git commit -m "feat: evolution_tools with disk patching, scoring, and lock management"
```

---

## Task 3: Evaluator Agent

**Files:**
- Create: `agents/evaluator_agent.py`
- Extend: `tests/test_autoresearcher.py` (start the file)

- [ ] **Step 3.1: Write failing test for evaluator fixture**

```python
# tests/test_autoresearcher.py
"""Integration tests for the autoresearcher evolution loop."""
import sqlite3, pytest, json
from pathlib import Path
import tools.evolution_db as edb
import tools.evolution_tools as et


@pytest.fixture
def evo(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.evolution_db.EVOLUTION_DB_PATH", tmp_path / "evo.db")
    monkeypatch.setattr("tools.evolution_tools.EVOLUTION_DB_PATH", tmp_path / "evo.db")
    edb.init_evolution_tables()
    return edb


def test_evaluator_agent_importable():
    from agents.evaluator_agent import evaluator_agent
    assert evaluator_agent.name == "evaluator_agent"
```

- [ ] **Step 3.2: Run to verify it fails**

```bash
pytest tests/test_autoresearcher.py::test_evaluator_agent_importable -v
```
Expected: `FAILED` — `ModuleNotFoundError`

- [ ] **Step 3.3: Implement `agents/evaluator_agent.py`**

```python
"""
Evaluator Agent — Quality Evaluator.
Scans unprocessed evolution_events, aggregates per-agent avg scores,
enqueues underperforming agents (avg < 6) into evaluator_queue.
Has its own reflection_agent for meta-evaluation of the flagged list.
"""
import os
from google.adk.agents import Agent
from agents.reflection_agent import make_reflection_agent
from tools.evolution_db import get_current_instruction
from tools.memory_tools import save_agent_output, recall_past_outputs

MODEL = os.getenv("MODEL_ID", "gemini-2.0-flash")
SCORE_THRESHOLD = float(os.getenv("EVALUATOR_SCORE_THRESHOLD", "6.0"))

INSTRUCTION_STATIC = """
You are the Quality Evaluator for a self-evolving multi-agent system.

## Your Two Modes

### Monitor Mode (auto-triggered)
1. Call `get_unprocessed_events()` to fetch all unprocessed evolution_events
2. Group by agent_name. For each agent, compute avg score of its unprocessed events
3. For agents with avg score < SCORE_THRESHOLD (default 6.0):
   a. Collect the 3-5 worst output_samples as evidence
   b. Call `enqueue_agent(agent_name, avg_score, evidence_list)`
   c. Call `mark_event_processed(event_id)` for each consumed event
4. Call `save_agent_output("evaluator_agent", flagged_summary)` with JSON summary

### Query Mode (user "evolution status")
1. Call `get_version_history(agent_name)` for all known agents
2. Call `dequeue_next_agent()` to see queue status
3. Return a read-only summary — do NOT mark events as processed, do NOT modify the queue

## Output Format (Monitor Mode)
```
EVALUATOR REPORT
─────────────────────────────────────────
Events processed: N
Agents flagged:   M
─────────────────────────────────────────
FLAGGED:
• [agent_name]: avg_score=X.X, samples=[3]
• [agent_name]: avg_score=X.X, samples=[5]
─────────────────────────────────────────
```

## Reflection Rubric (for your own meta-reflection)
Your reflection_agent will score your flagged list on:
- Precision: each flagged agent has ≥3 bad output samples in evidence (max 4 pts)
- Recall: all agents with avg < threshold are included (max 3 pts)
- Evidence quality: samples are genuinely poor, not noise (max 3 pts)
Score < 6 → re-run with broader evidence window (2× the last_n parameter).
Max 2 reflection cycles.

## Rules
- Never rewrite agent instructions — only flag and enqueue
- Never run in query mode autonomously — only when user explicitly requests status
- Process all unprocessed events in a single invocation; do not loop internally
"""


def get_instruction(agent_name: str) -> str:
    dynamic = get_current_instruction(agent_name)
    return dynamic if dynamic is not None else INSTRUCTION_STATIC


_reflection = make_reflection_agent()

evaluator_agent = Agent(
    model=MODEL,
    name="evaluator_agent",
    description=(
        "Quality Evaluator. Scans all agent outputs via evolution_events, "
        "aggregates per-agent scores, and enqueues underperforming agents "
        "into evaluator_queue for improvement. Also provides evolution status in query mode."
    ),
    instruction=get_instruction("evaluator_agent"),
    sub_agents=[_reflection],
    tools=[
        # imported at runtime by the agent's instruction logic via tool callbacks
        # listed here so ADK registers them:
        save_agent_output,
        recall_past_outputs,
    ],
)
```

- [ ] **Step 3.4: Run the import test**

```bash
pytest tests/test_autoresearcher.py::test_evaluator_agent_importable -v
```
Expected: `PASSED`

- [ ] **Step 3.5: Commit**

```bash
git add agents/evaluator_agent.py tests/test_autoresearcher.py
git commit -m "feat: evaluator_agent — quality evaluator with monitor and query modes"
```

---

## Task 4: Hypothesis Agent

**Files:**
- Create: `agents/hypothesis_agent.py`
- Extend: `tests/test_autoresearcher.py`

- [ ] **Step 4.1: Write failing import test**

```python
# append to tests/test_autoresearcher.py
def test_hypothesis_agent_importable():
    from agents.hypothesis_agent import hypothesis_agent
    assert hypothesis_agent.name == "hypothesis_agent"
```

- [ ] **Step 4.2: Run to verify it fails**

```bash
pytest tests/test_autoresearcher.py::test_hypothesis_agent_importable -v
```
Expected: `FAILED`

- [ ] **Step 4.3: Implement `agents/hypothesis_agent.py`**

```python
"""
Hypothesis Agent — Improvement Researcher.
Reads flagged agent from evaluator_queue, diagnoses root cause,
generates a proposed new INSTRUCTION with confidence rating.
NEVER writes to disk — DB and memory only.
"""
import os
from google.adk.agents import Agent
from agents.reflection_agent import make_reflection_agent
from tools.evolution_db import get_current_instruction
from tools.memory_tools import save_agent_output, recall_past_outputs

MODEL = os.getenv("MODEL_ID", "gemini-2.0-flash")

INSTRUCTION_STATIC = """
You are the Improvement Researcher for a self-evolving multi-agent system.

## Your Job
For a given underperforming agent, diagnose WHY it's failing and write a better INSTRUCTION.

## Inputs (you will receive these via the orchestrator)
- agent_name: the agent to improve
- evidence: list of bad output samples with scores
- current_instruction: the agent's current INSTRUCTION string
- mode: "auto" (from evaluator_queue) or "manual" (direct user request)

## Process

### Auto Mode
1. Call `dequeue_next_agent()` to get the highest-priority agent from evaluator_queue
2. Call `get_current_instruction(agent_name)` to get active instruction (may be from DB or static)
3. Read the evidence samples provided in the queue entry
4. Analyze: what is the gap between what the instruction asks for and what the outputs show?
5. Generate a structured hypothesis

### Manual Mode
1. Use agent_name from the user's request directly (DO NOT call dequeue_next_agent)
2. Call `recall_past_outputs(agent_name)` to fetch recent output samples
3. If no samples found (None or empty list): abort with message:
   "No output history found for [agent_name]. The agent must have run at least 3 times."
4. If recall_past_outputs raises an exception: log to supervisor DLQ and abort with:
   "Could not retrieve output history. Manual improvement unavailable."
5. Generate hypothesis from available samples

## Hypothesis Format
```
ROOT CAUSE: [1-2 sentence diagnosis of what the instruction is missing or saying wrong]
GAPS IN CURRENT INSTRUCTION:
• [gap 1]
• [gap 2]
PROPOSED INSTRUCTION:
[Full new INSTRUCTION string — complete replacement, not a patch]
CONFIDENCE: [high | medium | low]
```

## Confidence Rules
- high: clear root cause, ≥3 consistent failure patterns, proposed fix directly addresses gaps
- medium: probable root cause, 1-2 patterns, proposed fix is reasonable but less certain
- low: unclear failure pattern, insufficient samples, or proposed instruction is speculative

## After Generating
1. Save hypothesis to hypotheses table via `insert_hypothesis(...)`
2. Call `save_agent_output("hypothesis_agent", hypothesis_record)`
3. If CONFIDENCE == low:
   - Call `update_queue_status(agent_name, "aborted")` (auto mode) or log to DLQ (manual)
   - Do NOT pass to rewriter
4. If CONFIDENCE == medium or high:
   - Call `update_queue_status(agent_name, "done", confidence)` (auto mode)
   - Pass hypothesis to rewriter_agent

## Reflection
Your reflection_agent will score your hypothesis. Threshold: 7/10 (higher than normal —
rewrites are high-stakes disk operations).
If score < 7: re-generate with same samples, max 2 cycles.
If both cycles score < 7: treat as low confidence → DLQ.

## Rules
- NEVER write to disk — that is rewriter_agent's exclusive job
- NEVER modify the evaluator_queue status except via update_queue_status()
- Always provide a complete INSTRUCTION replacement, never a partial diff
"""


def get_instruction(agent_name: str) -> str:
    dynamic = get_current_instruction(agent_name)
    return dynamic if dynamic is not None else INSTRUCTION_STATIC


_reflection = make_reflection_agent()

hypothesis_agent = Agent(
    model=MODEL,
    name="hypothesis_agent",
    description=(
        "Improvement Researcher. Reads underperforming agent from evaluator_queue, "
        "diagnoses root cause, and produces a full replacement INSTRUCTION with "
        "confidence rating. Never writes to disk."
    ),
    instruction=get_instruction("hypothesis_agent"),
    sub_agents=[_reflection],
    tools=[
        save_agent_output,
        recall_past_outputs,
    ],
)
```

- [ ] **Step 4.4: Run the import test**

```bash
pytest tests/test_autoresearcher.py::test_hypothesis_agent_importable -v
```
Expected: `PASSED`

- [ ] **Step 4.5: Commit**

```bash
git add agents/hypothesis_agent.py
git commit -m "feat: hypothesis_agent — improvement researcher with auto and manual modes"
```

---

## Task 5: Rewriter Agent

**Files:**
- Create: `agents/rewriter_agent.py`
- Extend: `tests/test_autoresearcher.py`

- [ ] **Step 5.1: Write failing import test**

```python
# append to tests/test_autoresearcher.py
def test_rewriter_agent_importable():
    from agents.rewriter_agent import rewriter_agent
    assert rewriter_agent.name == "rewriter_agent"
```

- [ ] **Step 5.2: Run to verify it fails**

```bash
pytest tests/test_autoresearcher.py::test_rewriter_agent_importable -v
```
Expected: `FAILED`

- [ ] **Step 5.3: Implement `agents/rewriter_agent.py`**

```python
"""
Rewriter Agent — Instruction Engineer.
Applies validated hypotheses to disk atomically.
Guards: 24h count, 30-day count, consecutive stable, lock.
"""
import os
from google.adk.agents import Agent
from tools.evolution_db import get_current_instruction
from tools.memory_tools import save_agent_output

MODEL = os.getenv("MODEL_ID", "gemini-2.0-flash")

INSTRUCTION_STATIC = """
You are the Instruction Engineer for a self-evolving multi-agent system.
Your job is to safely apply hypothesis-generated instruction rewrites to disk.

## Inputs
- agent_name: the agent to rewrite
- hypothesis_id: FK to hypotheses table
- proposed_instruction: the new INSTRUCTION string
- confidence: "high" or "medium" (low-confidence never reaches you)

## Process (follow exactly — no skipping steps)

1. Call `release_stale_locks()` — clean up any expired locks first
2. Call `get_rewrite_count(agent_name, hours=24)`:
   - If ≥ 3: call `push_dlq(...)` with reason "24h rewrite limit reached", ABORT
3. Call `get_rewrite_count(agent_name, hours=720)` (30 days):
   - If ≥ 5 AND `get_consecutive_stable_count(agent_name)` < 2:
     call `push_dlq(...)` with reason "30-day guard: needs human review", ABORT
4. Call `acquire_rewrite_lock(agent_name, next_version)`:
   - next_version = len(get_version_history(agent_name))
   - If returns False: log "lock held" and ABORT (another rewrite in progress)
5. Within a single operation: call `get_baseline_score(agent_name, last_n=10)`
   — this returns (score, sampled_at). Store both — baseline is locked at THIS moment.
6. Call `snapshot_instruction(agent_name, next_version, current_instruction,
   score_baseline, baseline_sampled_at, hypothesis_id)`
   — saves current version to DB before any disk change
7. Validate proposed_instruction: it must be non-empty and not start with def/class
   (instructions are prose, not code). If invalid: release lock, push DLQ, ABORT.
8. Call `patch_instruction(get_agent_file_path(agent_name), proposed_instruction)`
   — atomic disk write. If SyntaxError: release lock, push DLQ, ABORT.
9. Call `transition_version_status(agent_name, next_version, "pending_watch")` — already set by insert
   (this is a no-op but confirms status is correct)
10. Call `update_queue_status(agent_name, "done")` — remove from active queue processing
11. Call `save_agent_output("rewriter_agent", summary_dict)` — log to memory

## Output Summary Format
```
REWRITE APPLIED
─────────────────────────────────────────
Agent:          [agent_name]
Version:        [N] (was: [N-1])
Baseline score: [X.X] (sampled at [timestamp])
Hypothesis ID:  [id]
Status:         pending_watch
─────────────────────────────────────────
```

## Rules
- ALWAYS snapshot before patching — never write without a restore point
- ALWAYS validate syntax before patching — never corrupt a file
- On ANY error after acquiring lock: release lock before aborting
- Never proceed past a failed guard check
"""


def get_instruction(agent_name: str) -> str:
    dynamic = get_current_instruction(agent_name)
    return dynamic if dynamic is not None else INSTRUCTION_STATIC


rewriter_agent = Agent(
    model=MODEL,
    name="rewriter_agent",
    description=(
        "Instruction Engineer. Applies hypothesis-generated instruction rewrites "
        "to disk atomically. Enforces 24h/30-day guards, lock acquisition, "
        "baseline scoring, and syntax validation before writing."
    ),
    instruction=get_instruction("rewriter_agent"),
    tools=[
        save_agent_output,
    ],
)
```

- [ ] **Step 5.4: Run the import test**

```bash
pytest tests/test_autoresearcher.py::test_rewriter_agent_importable -v
```
Expected: `PASSED`

- [ ] **Step 5.5: Commit**

```bash
git add agents/rewriter_agent.py
git commit -m "feat: rewriter_agent — atomic instruction patching with guards"
```

---

## Task 6: Rollback Watchdog Agent

**Files:**
- Create: `agents/rollback_watchdog_agent.py`
- Extend: `tests/test_autoresearcher.py`

- [ ] **Step 6.1: Write failing import test**

```python
# append to tests/test_autoresearcher.py
def test_rollback_watchdog_importable():
    from agents.rollback_watchdog_agent import rollback_watchdog_agent
    assert rollback_watchdog_agent.name == "rollback_watchdog_agent"
```

- [ ] **Step 6.2: Run to verify it fails**

```bash
pytest tests/test_autoresearcher.py::test_rollback_watchdog_importable -v
```
Expected: `FAILED`

- [ ] **Step 6.3: Implement `agents/rollback_watchdog_agent.py`**

```python
"""
Rollback Watchdog Agent — Stability Monitor.
Polls pending_watch agent_versions, compares post-rewrite scores to baseline,
restores previous version if quality drops > 10%.
Invoked hourly by supervisor (not a daemon — stateless per invocation).
Also handles manual restore requests.
"""
import os
from google.adk.agents import Agent
from tools.evolution_db import get_current_instruction
from tools.memory_tools import save_agent_output

MODEL = os.getenv("MODEL_ID", "gemini-2.0-flash")
ROLLBACK_THRESHOLD = float(os.getenv("ROLLBACK_THRESHOLD", "0.10"))  # 10% drop
WATCH_TIMEOUT_HOURS = int(os.getenv("WATCH_TIMEOUT_HOURS", "48"))
WATCH_EXTEND_HOURS = int(os.getenv("WATCH_EXTEND_HOURS", "72"))
WATCH_N_OUTPUTS = int(os.getenv("WATCH_N_OUTPUTS", "5"))

INSTRUCTION_STATIC = """
You are the Stability Monitor for a self-evolving multi-agent system.

## Two Modes

### Auto Poll Mode (invoked hourly by supervisor via "autoresearcher:watchdog_poll")
For each pending_watch entry in agent_versions:

1. Read: agent_name, version, score_baseline, baseline_sampled_at, created_at
2. Call `get_post_rewrite_scores(agent_name, after_timestamp=baseline_sampled_at, n=5)`
3. Compute hours elapsed = (now - created_at) in hours

Decision logic:
- If 0 scores AND elapsed < 48h: do nothing (still within primary window)
- If 0 scores AND elapsed >= 48h AND elapsed < 72h: extend window (log "waiting for outputs")
- If 0 scores AND elapsed >= 72h:
  → mark stable (idle fallback), release lock, log idle alert event, continue
- If 1-4 scores AND elapsed >= 48h OR scores >= 5:
  → compare avg(post_scores) vs score_baseline
  → if drop > ROLLBACK_THRESHOLD (10%): ROLLBACK (see rollback procedure below)
  → else: MARK STABLE

### Manual Restore Mode ("rollback [agent_name]" / "restore version N")
Direct user command — bypass all polling and guards:
1. Determine target_version (from user) or use most recent stable/superseded row before current
2. Call `restore_instruction(agent_name, target_version)`
3. If no prior version exists: abort with "No prior version found for [agent_name]"
4. If INSTRUCTION_STATIC restore needed (no DB row): insert version 0 with status=stable first
5. Release rewrite lock if held
6. Save verdict to memory

## Rollback Procedure
1. Find prior_row = most recent entry in agent_versions where version < current AND status IN ('stable','superseded')
2. If no prior_row found: read INSTRUCTION_STATIC from agent file, insert as version 0 with status=stable
3. Call `restore_instruction(agent_name, prior_version)`
   — this patches disk AND transitions prior_version → stable
4. Call `transition_version_status(agent_name, current_version, "rolled_back")`
5. Call `supersede_prior_versions` is NOT needed (rollback only affects these two rows)
6. Call `release_rewrite_lock(agent_name)`
7. Call `save_agent_output("rollback_watchdog_agent", verdict)`

## Mark Stable Procedure
1. Call `transition_version_status(agent_name, current_version, "stable")`
2. Call `supersede_prior_versions(agent_name, current_version)` — mark older stable as superseded
3. Call `release_rewrite_lock(agent_name)`
4. Call `save_agent_output("rollback_watchdog_agent", verdict)`

## Output Format
```
WATCHDOG VERDICT
─────────────────────────────────────────
Agent:          [agent_name]
Version:        [N]
Baseline score: [X.X]
Post scores:    [list] → avg [Y.Y]
Decision:       STABLE | ROLLED_BACK | WAITING | IDLE_TIMEOUT
─────────────────────────────────────────
```
"""


def get_instruction(agent_name: str) -> str:
    dynamic = get_current_instruction(agent_name)
    return dynamic if dynamic is not None else INSTRUCTION_STATIC


rollback_watchdog_agent = Agent(
    model=MODEL,
    name="rollback_watchdog_agent",
    description=(
        "Stability Monitor. Polls pending_watch agent versions, compares post-rewrite "
        "quality to baseline, and rolls back if quality drops > 10%. "
        "Also handles manual restore requests."
    ),
    instruction=get_instruction("rollback_watchdog_agent"),
    tools=[
        save_agent_output,
    ],
)
```

- [ ] **Step 6.4: Run the import test**

```bash
pytest tests/test_autoresearcher.py::test_rollback_watchdog_importable -v
```
Expected: `PASSED`

- [ ] **Step 6.5: Commit**

```bash
git add agents/rollback_watchdog_agent.py
git commit -m "feat: rollback_watchdog_agent — stability monitor with auto-poll and manual restore"
```

---

## Task 7: Autoresearcher Orchestrator

**Files:**
- Create: `agents/autoresearcher_orchestrator_agent.py`
- Extend: `tests/test_autoresearcher.py`

- [ ] **Step 7.1: Write failing import test**

```python
# append to tests/test_autoresearcher.py
def test_autoresearcher_orchestrator_importable():
    from agents.autoresearcher_orchestrator_agent import autoresearcher_orchestrator
    assert autoresearcher_orchestrator.name == "autoresearcher_orchestrator"
    # Must have 4 sub_agents
    assert len(autoresearcher_orchestrator.sub_agents) == 4
```

- [ ] **Step 7.2: Run to verify it fails**

```bash
pytest tests/test_autoresearcher.py::test_autoresearcher_orchestrator_importable -v
```
Expected: `FAILED`

- [ ] **Step 7.3: Implement `agents/autoresearcher_orchestrator_agent.py`**

```python
"""
Autoresearcher Orchestrator — self-evolving agent department root.
Routes to evaluator, hypothesis, rewriter, and watchdog agents.
Wired into company_orchestrator as a peer department.
"""
import os
from google.adk.agents import Agent
from agents.evaluator_agent import evaluator_agent
from agents.hypothesis_agent import hypothesis_agent
from agents.rewriter_agent import rewriter_agent
from agents.rollback_watchdog_agent import rollback_watchdog_agent
from agents.reflection_agent import make_reflection_agent
from tools.evolution_db import get_current_instruction
from tools.memory_tools import save_agent_output, recall_past_outputs

MODEL = os.getenv("MODEL_ID", "gemini-2.0-flash")
_reflection = make_reflection_agent()

INSTRUCTION_STATIC = """
You are the Autoresearcher Orchestrator — the self-evolving department that continuously
improves all other agents in the system by rewriting their instructions when quality drops.

## Your Team

| Agent | Role | When to use |
|---|---|---|
| evaluator_agent | Quality Evaluator | Monitor scores, flag underperformers, query history |
| hypothesis_agent | Improvement Researcher | Diagnose root cause, write new instructions |
| rewriter_agent | Instruction Engineer | Apply rewrites to disk with guards |
| rollback_watchdog_agent | Stability Monitor | Watch post-rewrite quality, restore if worse |

## Routing Logic

Route to **evaluator_agent** when:
- message is "autoresearcher:batch_review" (supervisor periodic trigger)
- "evaluate agents" / "quality review" / "batch analysis"
- "evolution status" / "what changed" / "version history" / "what's underperforming"

Route to **hypothesis_agent** then automatically **rewriter_agent** then **rollback_watchdog_agent** when:
- "improve [agent_name]" / "rewrite instruction" / "fix [agent_name]"
- After evaluator returns flagged agents (auto-loop: evaluator → hypothesis → rewriter → watchdog)

Route to **rollback_watchdog_agent** when:
- message is "autoresearcher:watchdog_poll" (supervisor hourly trigger)
- "rollback [agent_name]" / "restore version" / "undo last rewrite"

## Full Auto Loop (triggered by batch_review or low-score event)
1. Route to evaluator_agent (monitor mode) → get flagged list
2. For each flagged agent (from evaluator_queue, in priority order):
   a. Route to hypothesis_agent → get hypothesis
   b. If confidence != low: route to rewriter_agent → apply rewrite
3. Route to rollback_watchdog_agent → process any pending_watch entries
4. Done — loop returns to step 1 on next trigger

## Manual Loop ("improve [agent_name]")
1. Route to hypothesis_agent (manual mode, agent_name as parameter)
2. If confidence != low: route to rewriter_agent
3. Route to rollback_watchdog_agent (will pick up pending_watch on next hourly poll)

## Memory Protocol
- Session start: `recall_past_outputs("autoresearcher_orchestrator")` — surface recent history
- After each specialist completes: that specialist saves its own output to memory

## Quality Standards
- Never skip rewriter guards — 24h and 30-day limits are safety rails
- Never allow two simultaneous rewrites on the same agent (enforced by lock)
- Always route rollback_watchdog after rewriter — never leave pending_watch entries unmonitored
"""


def get_instruction(agent_name: str) -> str:
    dynamic = get_current_instruction(agent_name)
    return dynamic if dynamic is not None else INSTRUCTION_STATIC


autoresearcher_orchestrator = Agent(
    model=MODEL,
    name="autoresearcher_orchestrator",
    description=(
        "Self-evolving department that monitors all agent outputs, identifies "
        "underperformers, rewrites their instructions, and auto-rolls back if quality drops. "
        "Routes to evaluator, hypothesis, rewriter, and watchdog agents."
    ),
    instruction=get_instruction("autoresearcher_orchestrator"),
    sub_agents=[
        evaluator_agent,
        hypothesis_agent,
        rewriter_agent,
        rollback_watchdog_agent,
        _reflection,
    ],
    tools=[
        save_agent_output,
        recall_past_outputs,
    ],
)
```

- [ ] **Step 7.4: Run the import test**

```bash
pytest tests/test_autoresearcher.py::test_autoresearcher_orchestrator_importable -v
```
Expected: `PASSED`

- [ ] **Step 7.5: Commit**

```bash
git add agents/autoresearcher_orchestrator_agent.py
git commit -m "feat: autoresearcher_orchestrator — department root wiring all 4 specialists"
```

---

## Task 8: Wire into company_orchestrator

**Files:**
- Modify: `agents/company_orchestrator_agent.py`

- [ ] **Step 8.1: Add autoresearcher import and routing to company_orchestrator**

In `agents/company_orchestrator_agent.py`:

1. Add import after existing imports:
```python
from agents.autoresearcher_orchestrator_agent import autoresearcher_orchestrator
```

2. Add routing block to `INSTRUCTION` (after the `## Routing Logic` section, before existing routes):
```python
Route to **Autoresearcher Department** when:
- message starts with "autoresearcher:" (internal supervisor trigger — batch_review or watchdog_poll)
- "improve agents" / "evolve" / "quality review" / "what's underperforming"
- "rollback" / "restore" / "[agent_name] is performing badly" / "undo last rewrite"
- "evolution status" / "what changed" / "version history"
```

3. Add to `sub_agents` list:
```python
sub_agents=[
    marketing_orchestrator,
    sales_orchestrator,
    product_orchestrator,
    autoresearcher_orchestrator,  # ← add this
],
```

- [ ] **Step 8.2: Verify import chain works**

```bash
cd /Users/bhanu.prakash/Documents/claude_works/sl_agents/aass_agents
python -c "from agents.company_orchestrator_agent import company_orchestrator; print('OK')"
```
Expected: `OK`

- [ ] **Step 8.3: Commit**

```bash
git add agents/company_orchestrator_agent.py
git commit -m "feat: wire autoresearcher_orchestrator into company_orchestrator"
```

---

## Task 9: Supervisor Integration — Task Counter + Watchdog Poll

**Files:**
- Modify: `tools/supervisor.py`

- [ ] **Step 9.1: Read current supervisor.py to understand existing structure**

```bash
head -80 tools/supervisor.py
```

- [ ] **Step 9.2: Add task counter trigger and watchdog thread**

Locate the task completion logic in `supervisor.py`. Add:

```python
import os
import threading
import time

AUTORESEARCHER_BATCH_INTERVAL = int(os.getenv("AUTORESEARCHER_BATCH_INTERVAL", "20"))
WATCHDOG_POLL_INTERVAL_SECONDS = int(os.getenv("WATCHDOG_POLL_INTERVAL_SECONDS", "3600"))  # 1 hour

# In PipelineRun or wherever task completion is tracked:
def _on_task_complete(self):
    """Call after each task completes. Triggers autoresearcher batch review every N tasks."""
    self._task_count = getattr(self, "_task_count", 0) + 1
    if self._task_count % AUTORESEARCHER_BATCH_INTERVAL == 0:
        # Import here to avoid circular at module load
        from agents.company_orchestrator_agent import company_orchestrator
        # Route blocking — evaluator runs to completion before returning
        company_orchestrator.route("autoresearcher:batch_review")


def start_watchdog_poll_thread(company_orch):
    """Spawn background thread that invokes watchdog every WATCHDOG_POLL_INTERVAL_SECONDS."""
    def _loop():
        while True:
            time.sleep(WATCHDOG_POLL_INTERVAL_SECONDS)
            try:
                company_orch.route("autoresearcher:watchdog_poll")
            except Exception as e:
                # Don't crash supervisor if watchdog fails
                print(f"[watchdog] poll error: {e}")
    t = threading.Thread(target=_loop, daemon=True, name="watchdog-poll")
    t.start()
    return t
```

- [ ] **Step 9.3: Verify supervisor.py still imports cleanly**

```bash
python -c "from tools.supervisor import PipelineRun; print('OK')"
```
Expected: `OK`

- [ ] **Step 9.4: Commit**

```bash
git add tools/supervisor.py
git commit -m "feat: supervisor task counter trigger and watchdog poll thread"
```

---

## Task 10: Add Dynamic Instruction Loading to Existing Agents

**Files:**
- Modify: `agents/lead_researcher_agent.py`, `agents/outreach_composer_agent.py`,
  `agents/sales_call_prep_agent.py`, `agents/objection_handler_agent.py`,
  `agents/proposal_generator_agent.py`, `agents/crm_updater_agent.py`,
  `agents/deal_analyst_agent.py`

Each agent gets the same 3-line change. Pattern (do for each agent file):

- [ ] **Step 10.1: Update `agents/lead_researcher_agent.py`**

1. Rename `INSTRUCTION` → `INSTRUCTION_STATIC` (find and replace the variable name in the assignment)
2. Add after the `INSTRUCTION_STATIC` block:
```python
from tools.evolution_db import get_current_instruction

def _get_instruction() -> str:
    dynamic = get_current_instruction("lead_researcher_agent")
    return dynamic if dynamic is not None else INSTRUCTION_STATIC
```
3. Update the `Agent(...)` call: `instruction=_get_instruction()`

- [ ] **Step 10.2: Repeat for remaining 6 agent files**

Same pattern for each:
- `agents/outreach_composer_agent.py` → `get_current_instruction("outreach_composer_agent")`
- `agents/sales_call_prep_agent.py` → `get_current_instruction("sales_call_prep_agent")`
- `agents/objection_handler_agent.py` → `get_current_instruction("objection_handler_agent")`
- `agents/proposal_generator_agent.py` → `get_current_instruction("proposal_generator_agent")`
- `agents/crm_updater_agent.py` → `get_current_instruction("crm_updater_agent")`
- `agents/deal_analyst_agent.py` → `get_current_instruction("deal_analyst_agent")`

- [ ] **Step 10.3: Verify import chain**

```bash
python -c "
from agents.lead_researcher_agent import lead_researcher_agent
from agents.outreach_composer_agent import outreach_composer_agent
print('All agents import OK')
"
```
Expected: `All agents import OK`

- [ ] **Step 10.4: Commit**

```bash
git add agents/lead_researcher_agent.py agents/outreach_composer_agent.py \
        agents/sales_call_prep_agent.py agents/objection_handler_agent.py \
        agents/proposal_generator_agent.py agents/crm_updater_agent.py \
        agents/deal_analyst_agent.py
git commit -m "feat: add dynamic instruction hot-reload to all GTM agents"
```

---

## Task 11: Integration Tests — Full Evolution Loop

**Files:**
- Extend: `tests/test_autoresearcher.py`

- [ ] **Step 11.1: Write lock contention integration test**

```python
# append to tests/test_autoresearcher.py

def test_lock_contention_second_acquire_fails(evo):
    assert evo.acquire_rewrite_lock("some_agent", 1) is True
    assert evo.acquire_rewrite_lock("some_agent", 2) is False


def test_24h_rewrite_guard(evo):
    for v in range(3):
        evo.insert_version("guarded_agent", v, f"v{v}", None, None, None)
    assert evo.get_rewrite_count("guarded_agent", hours=24) == 3


def test_30d_guard_consecutive_stable(evo):
    evo.insert_version("a", 0, "v0", None, None, None)
    evo.transition_version_status("a", 0, "stable")
    evo.insert_version("a", 1, "v1", None, None, None)
    evo.transition_version_status("a", 1, "stable")
    assert evo.get_consecutive_stable_count("a") == 2


def test_rollback_path_via_tools(evo, tmp_path, monkeypatch):
    import tools.evolution_tools as et
    monkeypatch.setattr("tools.evolution_tools.AGENTS_DIR", str(tmp_path))
    monkeypatch.setattr("tools.evolution_db.EVOLUTION_DB_PATH", tmp_path / "evo.db")
    monkeypatch.setattr("tools.evolution_tools.EVOLUTION_DB_PATH", tmp_path / "evo.db")

    # Create agent fixture file
    agent_file = tmp_path / "my_agent.py"
    agent_file.write_text(
        '"""Agent."""\nINSTRUCTION_STATIC = """Original instruction."""\n'
    )
    # Snapshot v0 as stable
    et.snapshot_instruction("my_agent", 0, "Original instruction.", 7.0, None, None)
    evo.transition_version_status("my_agent", 0, "stable")
    # Rewrite to v1
    et.patch_instruction(str(agent_file), "New worse instruction.")
    et.snapshot_instruction("my_agent", 1, "New worse instruction.", 7.0, None, None)
    # Simulate: watchdog detects drop → restore v0
    et.restore_instruction("my_agent", 0)
    content = agent_file.read_text()
    assert "Original instruction." in content


def test_event_processed_cas_idempotent(evo):
    eid = evo.insert_evolution_event("a", "reflection_score", 3.0, "bad")
    r1 = evo.mark_event_processed(eid)
    r2 = evo.mark_event_processed(eid)
    assert r1 is True and r2 is False


def test_invalid_transition_raises(evo):
    from tools.evolution_db import InvalidStateTransition
    evo.insert_version("a", 0, "v0", None, None, None)
    evo.transition_version_status("a", 0, "rolled_back")
    with pytest.raises(InvalidStateTransition):
        evo.transition_version_status("a", 0, "stable")


def test_restore_to_instruction_static_inserts_v0(evo, tmp_path, monkeypatch):
    import tools.evolution_tools as et
    monkeypatch.setattr("tools.evolution_tools.AGENTS_DIR", str(tmp_path))
    agent_file = tmp_path / "fresh_agent.py"
    agent_file.write_text(
        '"""Agent."""\nINSTRUCTION_STATIC = """Original."""\n'
    )
    # No prior DB versions — restoring v0 should insert it
    et.snapshot_instruction("fresh_agent", 0, "Original.", 7.0, None, None)
    evo.transition_version_status("fresh_agent", 0, "stable")
    assert evo.get_current_instruction("fresh_agent") == "Original."
```

- [ ] **Step 11.2: Run all integration tests**

```bash
pytest tests/test_autoresearcher.py -v
```
Expected: all PASSED

- [ ] **Step 11.3: Run full test suite**

```bash
pytest tests/ -v --tb=short
```
Expected: all previously passing tests still pass, plus new autoresearcher tests

- [ ] **Step 11.4: Check coverage**

```bash
pytest tests/test_evolution_db.py tests/test_evolution_tools.py tests/test_autoresearcher.py \
  --cov=tools/evolution_db --cov=tools/evolution_tools --cov-report=term-missing
```
Expected: coverage ≥ 80% on both modules

- [ ] **Step 11.5: Commit**

```bash
git add tests/test_autoresearcher.py
git commit -m "test: integration tests for autoresearcher loop, rollback, guards, and CAS"
```

---

## Task 12: Final Wiring Verification

- [ ] **Step 12.1: Verify full import chain**

```bash
python -c "
from agents.company_orchestrator_agent import company_orchestrator
print('company_orchestrator sub_agents:', [a.name for a in company_orchestrator.sub_agents])
"
```
Expected output includes `autoresearcher_orchestrator`

- [ ] **Step 12.2: Verify evolution DB initializes alongside supervisor DB**

In `main.py` (or wherever `init_supervisor_tables()` is called), add:
```python
from tools.evolution_db import init_evolution_tables
init_evolution_tables()
```

- [ ] **Step 12.3: Verify main.py starts cleanly**

```bash
python -c "import main; print('main.py imports OK')"
```
Expected: `main.py imports OK`

- [ ] **Step 12.4: Final commit**

```bash
git add main.py
git commit -m "feat: initialize evolution_db alongside supervisor_db on startup"
```

---

## Summary

| Task | Deliverable | Tests |
|---|---|---|
| 1 | `evolution_db.py` — 5 tables + CRUD | `test_evolution_db.py` — 12 tests |
| 2 | `evolution_tools.py` — disk ops + scoring | `test_evolution_tools.py` — 8 tests |
| 3-6 | 4 specialist agents | 4 import tests |
| 7 | `autoresearcher_orchestrator_agent.py` | 1 structural test |
| 8 | `company_orchestrator_agent.py` updated | manual import verification |
| 9 | `supervisor.py` updated | manual import verification |
| 10 | 7 existing agents updated with hot-reload | manual import verification |
| 11 | Integration tests | 7 integration tests |
| 12 | `main.py` wired | startup verification |
