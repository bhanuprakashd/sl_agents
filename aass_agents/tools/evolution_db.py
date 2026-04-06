"""
Evolution DB — schema init and CRUD helpers for the autoresearcher self-evolving loop.

Tables:
  - agent_versions      : version history, one row per instruction version per agent
  - evolution_events    : score signals feeding the evolution loop
  - hypotheses          : root cause + proposed instruction records
  - evaluator_queue     : durable priority queue for evaluator→hypothesis handoff
  - rewrite_locks       : per-agent mutex preventing concurrent rewrites
  - candidate_pool      : population-based evolution with UCB1 sampling (ASI-Evolve)

All writes use asyncio.to_thread to avoid blocking the event loop.
SQLite opened in WAL mode for safe concurrent access.
"""
import math
import sqlite3
import asyncio
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

EVOLUTION_DB_PATH = Path(__file__).parent.parent / "evolution.db"

DDL = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS agent_versions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_name          TEXT NOT NULL,
    version             INTEGER NOT NULL,
    instruction_text    TEXT NOT NULL,
    score_baseline      REAL,
    baseline_sampled_at TEXT,
    status              TEXT DEFAULT 'pending_watch',
    hypothesis_id       INTEGER,
    created_at          TEXT NOT NULL,
    UNIQUE(agent_name, version)
);

CREATE TABLE IF NOT EXISTS evolution_events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_name    TEXT NOT NULL,
    trigger_type  TEXT NOT NULL,
    score         REAL NOT NULL,
    output_sample TEXT,
    processed     INTEGER DEFAULT 0,
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

CREATE TABLE IF NOT EXISTS evaluator_queue (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_name  TEXT NOT NULL UNIQUE,
    priority    REAL NOT NULL,
    evidence    TEXT NOT NULL,
    confidence  TEXT,
    queued_at   TEXT NOT NULL,
    status      TEXT DEFAULT 'pending'
);

CREATE TABLE IF NOT EXISTS rewrite_locks (
    agent_name  TEXT PRIMARY KEY,
    locked_at   TEXT NOT NULL,
    expires_at  TEXT NOT NULL,
    version     INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS candidate_pool (
    id              TEXT PRIMARY KEY,
    agent_name      TEXT NOT NULL,
    instruction     TEXT NOT NULL,
    fitness_score   REAL DEFAULT 0.0,
    visit_count     INTEGER DEFAULT 0,
    total_reward    REAL DEFAULT 0.0,
    parent_id       TEXT,
    generation      INTEGER DEFAULT 0,
    status          TEXT DEFAULT 'active',
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_candidate_pool_agent
    ON candidate_pool(agent_name, status);
"""

VALID_TRANSITIONS = {
    "pending_watch": {"stable", "rolled_back"},
    "stable": {"superseded"},
    "superseded": {"stable"},
    "rolled_back": set(),
}


class InvalidStateTransition(Exception):
    pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(EVOLUTION_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """Create all tables if they do not exist."""
    with _connect() as conn:
        conn.executescript(DDL)


async def async_init_db() -> None:
    await asyncio.to_thread(init_db)


# ── agent_versions ────────────────────────────────────────────────────────────

def get_current_instruction_sync(agent_name: str) -> Optional[str]:
    """Return most recent stable or pending_watch instruction, or None."""
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT instruction_text FROM agent_versions
            WHERE agent_name = ? AND status IN ('stable', 'pending_watch')
            ORDER BY version DESC LIMIT 1
            """,
            (agent_name,),
        ).fetchone()
    return row["instruction_text"] if row else None


async def get_current_instruction(agent_name: str) -> Optional[str]:
    return await asyncio.to_thread(get_current_instruction_sync, agent_name)


def snapshot_instruction_sync(
    agent_name: str,
    version: int,
    instruction_text: str,
    score_baseline: Optional[float],
    baseline_sampled_at: Optional[str],
    hypothesis_id: Optional[int],
) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO agent_versions
              (agent_name, version, instruction_text, score_baseline,
               baseline_sampled_at, status, hypothesis_id, created_at)
            VALUES (?, ?, ?, ?, ?, 'pending_watch', ?, ?)
            """,
            (agent_name, version, instruction_text, score_baseline,
             baseline_sampled_at, hypothesis_id, _now_iso()),
        )


async def snapshot_instruction(
    agent_name: str,
    version: int,
    instruction_text: str,
    score_baseline: Optional[float],
    baseline_sampled_at: Optional[str],
    hypothesis_id: Optional[int],
) -> None:
    await asyncio.to_thread(
        snapshot_instruction_sync,
        agent_name, version, instruction_text,
        score_baseline, baseline_sampled_at, hypothesis_id,
    )


def _validate_transition(current: str, target: str, agent_name: str, version: int) -> None:
    if target not in VALID_TRANSITIONS.get(current, set()):
        raise InvalidStateTransition(
            f"Invalid transition for {agent_name} v{version}: {current!r} → {target!r}"
        )


def update_version_status_sync(agent_name: str, version: int, new_status: str) -> None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT status FROM agent_versions WHERE agent_name=? AND version=?",
            (agent_name, version),
        ).fetchone()
        if not row:
            raise ValueError(f"No version {version} for agent {agent_name!r}")
        _validate_transition(row["status"], new_status, agent_name, version)
        conn.execute(
            "UPDATE agent_versions SET status=? WHERE agent_name=? AND version=?",
            (new_status, agent_name, version),
        )


async def update_version_status(agent_name: str, version: int, new_status: str) -> None:
    await asyncio.to_thread(update_version_status_sync, agent_name, version, new_status)


def get_pending_watch_sync() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM agent_versions WHERE status='pending_watch' ORDER BY created_at"
        ).fetchall()
    return [dict(r) for r in rows]


async def get_pending_watch() -> list[dict]:
    return await asyncio.to_thread(get_pending_watch_sync)


def get_evolution_history_sync(agent_name: str) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM agent_versions WHERE agent_name=? ORDER BY version DESC",
            (agent_name,),
        ).fetchall()
    return [dict(r) for r in rows]


async def get_evolution_history(agent_name: str) -> list[dict]:
    return await asyncio.to_thread(get_evolution_history_sync, agent_name)


def get_next_version_sync(agent_name: str) -> int:
    with _connect() as conn:
        row = conn.execute(
            "SELECT MAX(version) AS max_v FROM agent_versions WHERE agent_name=?",
            (agent_name,),
        ).fetchone()
    return (row["max_v"] + 1) if row and row["max_v"] is not None else 1


async def get_next_version(agent_name: str) -> int:
    return await asyncio.to_thread(get_next_version_sync, agent_name)


def get_rewrite_count_last_24h_sync(agent_name: str) -> int:
    cutoff = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    # subtract 24h manually via SQL
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS cnt FROM agent_versions
            WHERE agent_name=? AND created_at >= datetime(?, '-24 hours')
            """,
            (agent_name, cutoff),
        ).fetchone()
    return row["cnt"] if row else 0


async def get_rewrite_count_last_24h(agent_name: str) -> int:
    return await asyncio.to_thread(get_rewrite_count_last_24h_sync, agent_name)


def get_rewrite_count_last_30d_sync(agent_name: str) -> int:
    cutoff = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS cnt FROM agent_versions
            WHERE agent_name=? AND created_at >= datetime(?, '-30 days')
            """,
            (agent_name, cutoff),
        ).fetchone()
    return row["cnt"] if row else 0


async def get_rewrite_count_last_30d(agent_name: str) -> int:
    return await asyncio.to_thread(get_rewrite_count_last_30d_sync, agent_name)


def get_consecutive_stable_count_sync(agent_name: str) -> int:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT status FROM agent_versions
            WHERE agent_name=? AND status IN ('stable', 'rolled_back')
            ORDER BY version DESC
            """,
            (agent_name,),
        ).fetchall()
    count = 0
    for row in rows:
        if row["status"] == "stable":
            count += 1
        else:
            break
    return count


async def get_consecutive_stable_count(agent_name: str) -> int:
    return await asyncio.to_thread(get_consecutive_stable_count_sync, agent_name)


# ── evolution_events ──────────────────────────────────────────────────────────

def log_evolution_event_sync(
    agent_name: str,
    trigger_type: str,
    score: float,
    output_sample: Optional[str] = None,
) -> None:
    sample = output_sample
    if sample and not isinstance(sample, str):
        sample = f"[binary output: {type(output_sample).__name__}]"
    if sample:
        sample = sample[:2000]
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO evolution_events
              (agent_name, trigger_type, score, output_sample, processed, created_at)
            VALUES (?, ?, ?, ?, 0, ?)
            """,
            (agent_name, trigger_type, score, sample, _now_iso()),
        )


async def log_evolution_event(
    agent_name: str,
    trigger_type: str,
    score: float,
    output_sample: Optional[str] = None,
) -> None:
    await asyncio.to_thread(
        log_evolution_event_sync, agent_name, trigger_type, score, output_sample
    )


def mark_event_processed_sync(event_id: int) -> bool:
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE evolution_events SET processed=1 WHERE id=? AND processed=0",
            (event_id,),
        )
    return cur.rowcount == 1


async def mark_event_processed(event_id: int) -> bool:
    return await asyncio.to_thread(mark_event_processed_sync, event_id)


def get_unprocessed_events_sync(limit: int = 500) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM evolution_events WHERE processed=0 ORDER BY created_at LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


async def get_unprocessed_events(limit: int = 500) -> list[dict]:
    return await asyncio.to_thread(get_unprocessed_events_sync, limit)


def get_post_rewrite_scores_sync(
    agent_name: str, after_timestamp: str, n: int = 5
) -> list[float]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT score FROM evolution_events
            WHERE agent_name=? AND created_at > ?
            ORDER BY created_at LIMIT ?
            """,
            (agent_name, after_timestamp, n),
        ).fetchall()
    return [row["score"] for row in rows]


async def get_post_rewrite_scores(
    agent_name: str, after_timestamp: str, n: int = 5
) -> list[float]:
    return await asyncio.to_thread(get_post_rewrite_scores_sync, agent_name, after_timestamp, n)


def get_baseline_score_sync(agent_name: str, last_n: int = 10) -> tuple[float, str]:
    """Return (mean_score, sampled_at_timestamp). Raises ValueError if no events."""
    sampled_at = _now_iso()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT score FROM evolution_events
            WHERE agent_name=?
            ORDER BY created_at DESC LIMIT ?
            """,
            (agent_name, last_n),
        ).fetchall()
    if not rows:
        raise ValueError(f"No evolution events found for agent {agent_name!r}")
    scores = [r["score"] for r in rows]
    return sum(scores) / len(scores), sampled_at


async def get_baseline_score(agent_name: str, last_n: int = 10) -> tuple[float, str]:
    return await asyncio.to_thread(get_baseline_score_sync, agent_name, last_n)


# ── hypotheses ────────────────────────────────────────────────────────────────

def save_hypothesis_sync(
    agent_name: str,
    version: int,
    root_cause: str,
    hypothesis_text: str,
    confidence: str,
) -> int:
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO hypotheses
              (agent_name, version, root_cause, hypothesis_text, confidence, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (agent_name, version, root_cause, hypothesis_text, confidence, _now_iso()),
        )
        return cur.lastrowid


async def save_hypothesis(
    agent_name: str,
    version: int,
    root_cause: str,
    hypothesis_text: str,
    confidence: str,
) -> int:
    return await asyncio.to_thread(
        save_hypothesis_sync, agent_name, version, root_cause, hypothesis_text, confidence
    )


# ── evaluator_queue ───────────────────────────────────────────────────────────

def enqueue_agent_sync(
    agent_name: str, priority: float, evidence: list[dict]
) -> None:
    evidence_json = json.dumps(evidence)
    with _connect() as conn:
        existing = conn.execute(
            "SELECT priority FROM evaluator_queue WHERE agent_name=?",
            (agent_name,),
        ).fetchone()
        if existing:
            if priority < existing["priority"]:
                conn.execute(
                    "UPDATE evaluator_queue SET priority=?, evidence=?, queued_at=?, status='pending' WHERE agent_name=?",
                    (priority, evidence_json, _now_iso(), agent_name),
                )
        else:
            conn.execute(
                "INSERT INTO evaluator_queue (agent_name, priority, evidence, queued_at, status) VALUES (?,?,?,?,'pending')",
                (agent_name, priority, evidence_json, _now_iso()),
            )


async def enqueue_agent(
    agent_name: str, priority: float, evidence: list[dict]
) -> None:
    await asyncio.to_thread(enqueue_agent_sync, agent_name, priority, evidence)


def dequeue_next_agent_sync() -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM evaluator_queue
            WHERE status='done'
            ORDER BY
              CASE confidence WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
              priority ASC
            LIMIT 1
            """,
        ).fetchone()
    return dict(row) if row else None


async def dequeue_next_agent() -> Optional[dict]:
    return await asyncio.to_thread(dequeue_next_agent_sync)


def mark_queue_entry_done_sync(agent_name: str, confidence: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE evaluator_queue SET status='done', confidence=? WHERE agent_name=?",
            (confidence, agent_name),
        )


async def mark_queue_entry_done(agent_name: str, confidence: str) -> None:
    await asyncio.to_thread(mark_queue_entry_done_sync, agent_name, confidence)


def mark_queue_entry_aborted_sync(agent_name: str, reason: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE evaluator_queue SET status='aborted' WHERE agent_name=?",
            (agent_name,),
        )


async def mark_queue_entry_aborted(agent_name: str, reason: str) -> None:
    await asyncio.to_thread(mark_queue_entry_aborted_sync, agent_name, reason)


def get_queue_pending_sync() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM evaluator_queue WHERE status='pending' ORDER BY priority ASC"
        ).fetchall()
    return [dict(r) for r in rows]


async def get_queue_pending() -> list[dict]:
    return await asyncio.to_thread(get_queue_pending_sync)


# ── rewrite_locks ─────────────────────────────────────────────────────────────

def acquire_rewrite_lock_sync(agent_name: str, version: int) -> bool:
    now = _now_iso()
    # expires after 72h
    with _connect() as conn:
        # release stale locks first
        conn.execute(
            "DELETE FROM rewrite_locks WHERE expires_at < ?", (now,)
        )
        try:
            conn.execute(
                """
                INSERT INTO rewrite_locks (agent_name, locked_at, expires_at, version)
                VALUES (?, ?, datetime(?, '+72 hours'), ?)
                """,
                (agent_name, now, now, version),
            )
            return True
        except sqlite3.IntegrityError:
            return False


async def acquire_rewrite_lock(agent_name: str, version: int) -> bool:
    return await asyncio.to_thread(acquire_rewrite_lock_sync, agent_name, version)


def release_rewrite_lock_sync(agent_name: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM rewrite_locks WHERE agent_name=?", (agent_name,))


async def release_rewrite_lock(agent_name: str) -> None:
    await asyncio.to_thread(release_rewrite_lock_sync, agent_name)


def release_stale_locks_sync() -> int:
    now = _now_iso()
    with _connect() as conn:
        cur = conn.execute("DELETE FROM rewrite_locks WHERE expires_at < ?", (now,))
    return cur.rowcount


async def release_stale_locks() -> int:
    return await asyncio.to_thread(release_stale_locks_sync)


# ── candidate_pool (ASI-Evolve population-based evolution) ───────────────────

MAX_POPULATION = 10  # per agent
UCB1_C = 1.41  # exploration constant (sqrt(2) default)


def add_candidate_sync(
    agent_name: str,
    instruction: str,
    fitness_score: float = 0.0,
    parent_id: Optional[str] = None,
    generation: int = 0,
) -> str:
    """Insert a new candidate into the pool. Returns the generated id."""
    candidate_id = uuid.uuid4().hex
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO candidate_pool
              (id, agent_name, instruction, fitness_score, visit_count,
               total_reward, parent_id, generation, status, created_at)
            VALUES (?, ?, ?, ?, 0, 0.0, ?, ?, 'active', ?)
            """,
            (candidate_id, agent_name, instruction, fitness_score,
             parent_id, generation, _now_iso()),
        )
    return candidate_id


async def add_candidate(
    agent_name: str,
    instruction: str,
    fitness_score: float = 0.0,
    parent_id: Optional[str] = None,
    generation: int = 0,
) -> str:
    return await asyncio.to_thread(
        add_candidate_sync, agent_name, instruction,
        fitness_score, parent_id, generation,
    )


def get_active_candidates_sync(agent_name: str) -> list[dict]:
    """Return all active candidates for an agent, ordered by fitness descending."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM candidate_pool
            WHERE agent_name=? AND status='active'
            ORDER BY fitness_score DESC
            """,
            (agent_name,),
        ).fetchall()
    return [dict(r) for r in rows]


async def get_active_candidates(agent_name: str) -> list[dict]:
    return await asyncio.to_thread(get_active_candidates_sync, agent_name)


def sample_parent_ucb1_sync(agent_name: str, c: float = UCB1_C) -> Optional[dict]:
    """Select a parent candidate using UCB1 (exploration-exploitation balance).

    UCB1 score = avg_reward + c * sqrt(ln(total_visits) / visit_count)
    Returns the candidate with highest UCB1 score, or None if pool is empty.
    """
    candidates = get_active_candidates_sync(agent_name)
    if not candidates:
        return None

    total_visits = sum(cand["visit_count"] for cand in candidates)
    if total_visits == 0:
        # No visits yet — return the one with highest fitness
        return max(candidates, key=lambda x: x["fitness_score"])

    best = None
    best_score = -float("inf")
    for cand in candidates:
        if cand["visit_count"] == 0:
            # Unvisited candidates get infinite UCB1 — prioritize exploration
            return cand
        avg_reward = cand["total_reward"] / cand["visit_count"]
        exploration = c * math.sqrt(math.log(total_visits) / cand["visit_count"])
        ucb1_score = avg_reward + exploration
        if ucb1_score > best_score:
            best_score = ucb1_score
            best = cand
    return best


async def sample_parent_ucb1(agent_name: str, c: float = UCB1_C) -> Optional[dict]:
    return await asyncio.to_thread(sample_parent_ucb1_sync, agent_name, c)


def record_candidate_reward_sync(candidate_id: str, reward: float) -> None:
    """Record a reward signal for a candidate (increments visit_count and total_reward)."""
    with _connect() as conn:
        conn.execute(
            """
            UPDATE candidate_pool
            SET visit_count = visit_count + 1,
                total_reward = total_reward + ?,
                fitness_score = (total_reward + ?) / (visit_count + 1)
            WHERE id=?
            """,
            (reward, reward, candidate_id),
        )


async def record_candidate_reward(candidate_id: str, reward: float) -> None:
    await asyncio.to_thread(record_candidate_reward_sync, candidate_id, reward)


def maintain_population_sync(agent_name: str, max_pop: int = MAX_POPULATION) -> int:
    """Retire lowest-performing candidates if pool exceeds max_pop.

    Only retires candidates with visit_count >= 5 and fitness below 25th percentile.
    Returns the number of candidates retired.
    """
    candidates = get_active_candidates_sync(agent_name)
    if len(candidates) <= max_pop:
        return 0

    # Only retire candidates with sufficient visits
    evaluated = [c for c in candidates if c["visit_count"] >= 5]
    if len(evaluated) < 4:
        return 0  # Need at least 4 evaluated to compute percentile

    scores = sorted([c["fitness_score"] for c in evaluated])
    p25 = scores[len(scores) // 4]

    retired = 0
    with _connect() as conn:
        for cand in evaluated:
            if cand["fitness_score"] < p25 and len(candidates) - retired > max_pop:
                conn.execute(
                    "UPDATE candidate_pool SET status='retired' WHERE id=?",
                    (cand["id"],),
                )
                retired += 1
                if len(candidates) - retired <= max_pop:
                    break
    return retired


async def maintain_population(agent_name: str, max_pop: int = MAX_POPULATION) -> int:
    return await asyncio.to_thread(maintain_population_sync, agent_name, max_pop)


def get_champion_sync(agent_name: str) -> Optional[dict]:
    """Return the highest-fitness active candidate (champion)."""
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM candidate_pool
            WHERE agent_name=? AND status='active' AND visit_count >= 3
            ORDER BY fitness_score DESC
            LIMIT 1
            """,
            (agent_name,),
        ).fetchone()
    return dict(row) if row else None


async def get_champion(agent_name: str) -> Optional[dict]:
    return await asyncio.to_thread(get_champion_sync, agent_name)


def promote_champion_sync(agent_name: str) -> Optional[dict]:
    """Mark the current champion as 'champion' status and demote previous champion.

    Returns the promoted candidate, or None if no eligible champion found.
    """
    champion = get_champion_sync(agent_name)
    if not champion:
        return None

    with _connect() as conn:
        # Demote previous champions back to active
        conn.execute(
            "UPDATE candidate_pool SET status='active' WHERE agent_name=? AND status='champion'",
            (agent_name,),
        )
        # Promote new champion
        conn.execute(
            "UPDATE candidate_pool SET status='champion' WHERE id=?",
            (champion["id"],),
        )
    champion["status"] = "champion"
    return champion


async def promote_champion(agent_name: str) -> Optional[dict]:
    return await asyncio.to_thread(promote_champion_sync, agent_name)


def get_candidate_lineage_sync(candidate_id: str, depth: int = 10) -> list[dict]:
    """Trace the lineage of a candidate back through parent_id chain."""
    lineage = []
    current_id = candidate_id
    for _ in range(depth):
        with _connect() as conn:
            row = conn.execute(
                "SELECT * FROM candidate_pool WHERE id=?",
                (current_id,),
            ).fetchone()
        if not row:
            break
        lineage.append(dict(row))
        current_id = row["parent_id"]
        if not current_id:
            break
    return lineage


async def get_candidate_lineage(candidate_id: str, depth: int = 10) -> list[dict]:
    return await asyncio.to_thread(get_candidate_lineage_sync, candidate_id, depth)


# Init on import
init_db()
