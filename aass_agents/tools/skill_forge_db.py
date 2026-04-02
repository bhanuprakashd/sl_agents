"""
Skill Forge DB — schema init and CRUD helpers for the SKILL FORGE pipeline.

Tables:
  - forge_sessions      : session lifecycle, one row per skill generation run
  - research_bundles    : research swarm outputs per session
  - skill_versions      : versioned SKILL.md content with composite scores
  - battle_test_results : red team results per version
  - staging_registry    : promoted skills awaiting production

All writes are synchronous — ADK tools are sync.
SQLite opened in WAL mode for safe concurrent access.
"""
import sqlite3
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

SKILL_FORGE_DB_PATH = Path(__file__).parent.parent / "skill_forge.db"

DDL = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS forge_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_spec_json TEXT NOT NULL,
    current_stage TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS research_bundles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    researcher_type TEXT NOT NULL,
    findings_json TEXT NOT NULL,
    citations_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS skill_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    version INTEGER NOT NULL,
    skill_content TEXT NOT NULL,
    composite_score REAL NOT NULL DEFAULT 0.0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS battle_test_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    version INTEGER NOT NULL,
    pass_rate REAL NOT NULL,
    failure_breakdown_json TEXT NOT NULL,
    test_cases_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS staging_registry (
    skill_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    domain TEXT NOT NULL,
    department TEXT NOT NULL,
    file_path TEXT NOT NULL,
    composite_score REAL NOT NULL,
    needs_review INTEGER NOT NULL DEFAULT 0,
    production_runs INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(SKILL_FORGE_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """Create all tables if they do not exist."""
    with _connect() as conn:
        conn.executescript(DDL)


# ── forge_sessions ─────────────────────────────────────────────────────────────

def create_session_sync(task_spec: dict, current_stage: str) -> int:
    """Create a new forge session and return its ID."""
    now = _now_iso()
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO forge_sessions (task_spec_json, current_stage, status, created_at, updated_at)
            VALUES (?, ?, 'active', ?, ?)
            """,
            (json.dumps(task_spec), current_stage, now, now),
        )
        return cur.lastrowid


def update_session_stage_sync(session_id: int, stage: str) -> None:
    """Update the current stage of a forge session."""
    with _connect() as conn:
        conn.execute(
            "UPDATE forge_sessions SET current_stage=?, updated_at=? WHERE id=?",
            (stage, _now_iso(), session_id),
        )


def update_session_status_sync(session_id: int, status: str) -> None:
    """Update the status of a forge session."""
    with _connect() as conn:
        conn.execute(
            "UPDATE forge_sessions SET status=?, updated_at=? WHERE id=?",
            (status, _now_iso(), session_id),
        )


def get_session_sync(session_id: int) -> Optional[dict]:
    """Retrieve a forge session by ID, returning None if not found."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM forge_sessions WHERE id=?",
            (session_id,),
        ).fetchone()
    if row is None:
        return None
    result = dict(row)
    result["task_spec"] = json.loads(result["task_spec_json"])
    return result


# ── research_bundles ──────────────────────────────────────────────────────────

def save_research_bundle_sync(
    session_id: int,
    researcher_type: str,
    findings: dict,
    citations: list,
) -> None:
    """Save a research bundle for a session."""
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO research_bundles
              (session_id, researcher_type, findings_json, citations_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, researcher_type, json.dumps(findings), json.dumps(citations), _now_iso()),
        )


def get_research_bundles_sync(session_id: int) -> list[dict]:
    """Retrieve all research bundles for a session."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM research_bundles WHERE session_id=? ORDER BY created_at",
            (session_id,),
        ).fetchall()
    results = []
    for row in rows:
        entry = dict(row)
        entry["findings"] = json.loads(entry["findings_json"])
        entry["citations"] = json.loads(entry["citations_json"])
        results.append(entry)
    return results


# ── skill_versions ────────────────────────────────────────────────────────────

def save_skill_version_sync(
    session_id: int,
    version: int,
    skill_content: str,
    composite_score: float,
) -> int:
    """Save a skill version and return its ID."""
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO skill_versions
              (session_id, version, skill_content, composite_score, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, version, skill_content, composite_score, _now_iso()),
        )
        return cur.lastrowid


def get_best_skill_version_sync(session_id: int) -> Optional[dict]:
    """Return the skill version with the highest composite score for a session."""
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM skill_versions
            WHERE session_id=?
            ORDER BY composite_score DESC, version DESC
            LIMIT 1
            """,
            (session_id,),
        ).fetchone()
    return dict(row) if row else None


def get_skill_versions_sync(session_id: int) -> list[dict]:
    """Return all skill versions for a session, ordered by version ascending."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM skill_versions WHERE session_id=? ORDER BY version ASC",
            (session_id,),
        ).fetchall()
    return [dict(r) for r in rows]


# ── battle_test_results ───────────────────────────────────────────────────────

def save_battle_test_sync(
    session_id: int,
    version: int,
    pass_rate: float,
    failure_breakdown: dict,
    test_cases: list,
) -> None:
    """Save battle test results for a skill version."""
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO battle_test_results
              (session_id, version, pass_rate, failure_breakdown_json, test_cases_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                version,
                pass_rate,
                json.dumps(failure_breakdown),
                json.dumps(test_cases),
                _now_iso(),
            ),
        )


def get_battle_test_sync(session_id: int, version: int) -> Optional[dict]:
    """Retrieve battle test results for a specific session and version."""
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM battle_test_results
            WHERE session_id=? AND version=?
            ORDER BY created_at DESC LIMIT 1
            """,
            (session_id, version),
        ).fetchone()
    if row is None:
        return None
    result = dict(row)
    result["failure_breakdown"] = json.loads(result["failure_breakdown_json"])
    result["test_cases"] = json.loads(result["test_cases_json"])
    return result


# ── staging_registry ──────────────────────────────────────────────────────────

def stage_skill_sync(
    skill_id: str,
    name: str,
    domain: str,
    department: str,
    file_path: str,
    composite_score: float,
    needs_review: bool,
) -> None:
    """Insert or replace a skill entry in the staging registry."""
    now = _now_iso()
    needs_review_int = 1 if needs_review else 0
    with _connect() as conn:
        existing = conn.execute(
            "SELECT production_runs FROM staging_registry WHERE skill_id=?",
            (skill_id,),
        ).fetchone()
        production_runs = existing["production_runs"] if existing else 0
        conn.execute(
            """
            INSERT OR REPLACE INTO staging_registry
              (skill_id, name, domain, department, file_path, composite_score,
               needs_review, production_runs, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                skill_id, name, domain, department, file_path, composite_score,
                needs_review_int, production_runs,
                existing["production_runs"] if existing else now,
                now,
            ),
        )


def increment_production_runs_sync(skill_id: str) -> int:
    """Increment production_runs counter and return the new count."""
    with _connect() as conn:
        conn.execute(
            "UPDATE staging_registry SET production_runs = production_runs + 1, updated_at=? WHERE skill_id=?",
            (_now_iso(), skill_id),
        )
        row = conn.execute(
            "SELECT production_runs FROM staging_registry WHERE skill_id=?",
            (skill_id,),
        ).fetchone()
    return row["production_runs"] if row else 0


def get_staged_skill_sync(skill_id: str) -> Optional[dict]:
    """Retrieve a staged skill by ID."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM staging_registry WHERE skill_id=?",
            (skill_id,),
        ).fetchone()
    return dict(row) if row else None


def list_staged_skills_sync() -> list[dict]:
    """List all skills in the staging registry."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM staging_registry ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


# ── Skill Graduation Pipeline ────────────────────────────────────────────────
#
# Graduation path: staged → review → promoted → active
#
# Criteria for auto-promotion:
#   1. composite_score >= PROMOTION_SCORE_THRESHOLD
#   2. production_runs >= PROMOTION_RUN_THRESHOLD
#   3. needs_review == 0 (human review complete, or score high enough to skip)

PROMOTION_SCORE_THRESHOLD = 0.85
PROMOTION_RUN_THRESHOLD = 3
AUTO_PROMOTE_SCORE = 0.95  # Skip human review if score is this high


def check_promotion_eligible(skill_id: str) -> dict:
    """
    Check if a staged skill is eligible for promotion to active.

    Returns:
        dict with eligible (bool), reasons (list), and skill data
    """
    skill = get_staged_skill_sync(skill_id)
    if skill is None:
        return {"eligible": False, "reasons": ["Skill not found"], "skill": None}

    reasons: list[str] = []
    eligible = True

    score = skill["composite_score"]
    runs = skill["production_runs"]
    needs_review = skill["needs_review"]

    if score < PROMOTION_SCORE_THRESHOLD:
        eligible = False
        reasons.append(
            f"Score {score:.2f} < threshold {PROMOTION_SCORE_THRESHOLD}"
        )

    if runs < PROMOTION_RUN_THRESHOLD:
        eligible = False
        reasons.append(
            f"Production runs {runs} < threshold {PROMOTION_RUN_THRESHOLD}"
        )

    if needs_review and score < AUTO_PROMOTE_SCORE:
        eligible = False
        reasons.append(
            f"Needs human review (score {score:.2f} < auto-promote {AUTO_PROMOTE_SCORE})"
        )

    if eligible:
        reasons.append("All promotion criteria met")

    return {
        "eligible": eligible,
        "reasons": reasons,
        "skill": skill,
    }


def promote_skill_sync(skill_id: str) -> dict:
    """
    Promote a staged skill to active status.

    Copies the skill from staging_registry to a 'promoted' state
    and clears the needs_review flag.

    Returns:
        dict with success, message, and skill data
    """
    check = check_promotion_eligible(skill_id)
    if not check["eligible"]:
        return {
            "success": False,
            "message": f"Not eligible: {'; '.join(check['reasons'])}",
            "skill": check["skill"],
        }

    with _connect() as conn:
        conn.execute(
            """UPDATE staging_registry
               SET needs_review = 0, updated_at = ?
               WHERE skill_id = ?""",
            (_now_iso(), skill_id),
        )

    return {
        "success": True,
        "message": f"Skill '{skill_id}' promoted to active",
        "skill": get_staged_skill_sync(skill_id),
    }


def demote_skill_sync(skill_id: str, reason: str = "") -> dict:
    """
    Demote a skill back to review-needed state.

    Returns:
        dict with success and message
    """
    skill = get_staged_skill_sync(skill_id)
    if skill is None:
        return {"success": False, "message": "Skill not found"}

    with _connect() as conn:
        conn.execute(
            """UPDATE staging_registry
               SET needs_review = 1, production_runs = 0, updated_at = ?
               WHERE skill_id = ?""",
            (_now_iso(), skill_id),
        )

    return {
        "success": True,
        "message": f"Skill '{skill_id}' demoted. Reason: {reason or 'none given'}",
    }


def get_promotion_dashboard_sync() -> dict:
    """
    Get promotion status for all staged skills.

    Returns:
        dict with skills grouped by status (eligible, needs_review, not_ready)
    """
    skills = list_staged_skills_sync()

    eligible = []
    needs_review = []
    not_ready = []

    for skill in skills:
        check = check_promotion_eligible(skill["skill_id"])
        entry = {**skill, "promotion_check": check}

        if check["eligible"]:
            eligible.append(entry)
        elif skill["needs_review"]:
            needs_review.append(entry)
        else:
            not_ready.append(entry)

    return {
        "eligible": eligible,
        "needs_review": needs_review,
        "not_ready": not_ready,
        "total": len(skills),
    }


# Init on import
init_db()
