# SKILL FORGE Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a 12-agent pipeline that generates battle-tested Claude Code skills from a single NLP sentence, achieving top 1% human performance with automated G-Eval scoring.

**Architecture:** Four phases — Foundation (DB + models) → Research Pipeline (Intent Parser + Swarm + Synthesizer) → Generation Pipeline (Drafter + Critics) → Validation Pipeline (Red Team + Iteration + Promoter + Orchestrator). Each phase is independently testable. State persists in `skill_forge.db` so crashed runs resume automatically.

**Tech Stack:** Python 3.11+, Google ADK (`google.adk.agents.Agent`), SQLite (WAL mode), pytest, asyncio, frozen dataclasses, `aiofiles`

---

## File Map

```
aass_agents/
├── tools/
│   └── skill_forge_db.py          # DB schema + CRUD (mirrors evolution_db.py)
├── agents/skill_forge/
│   ├── __init__.py
│   ├── models.py                   # TaskSpec, ResearchBundle, ExpertBlueprint, etc.
│   ├── intent_parser_agent.py      # Stage 1: NLP → TaskSpec
│   ├── research_swarm_agent.py     # Stage 2: 3 parallel researchers
│   ├── expert_synthesizer_agent.py # Stage 3: bundles → ExpertBlueprint
│   ├── skill_drafter_agent.py      # Stage 4: blueprint → SKILL.md v0
│   ├── critic_panel_agent.py       # Stage 5: A-HMAD 3-critic debate
│   ├── red_team_agent.py           # Stage 6: 100-case battle test
│   ├── iteration_agent.py          # Stage 7: GEPA reflection loop
│   ├── promoter_agent.py           # Stage 8: confidence gate + staging
│   └── orchestrator_agent.py       # Top-level coordinator
├── skills/skill-forge/
│   └── SKILL.md                    # /forge trigger skill
└── tests/skill_forge/
    ├── test_skill_forge_db.py
    ├── test_models.py
    ├── test_intent_parser.py
    ├── test_research_swarm.py
    ├── test_expert_synthesizer.py
    ├── test_skill_drafter.py
    ├── test_critic_panel.py
    ├── test_red_team.py
    ├── test_iteration_agent.py
    ├── test_promoter.py
    └── test_orchestrator_e2e.py

generated_skills/                   # staging registry (repo root)
└── _registry.json
```

---

## Phase 1: Foundation

### Task 1: DB Schema + CRUD

**Files:**
- Create: `aass_agents/tools/skill_forge_db.py`
- Create: `aass_agents/tests/skill_forge/test_skill_forge_db.py`

- [ ] **Step 1: Write failing tests**

```python
# aass_agents/tests/skill_forge/test_skill_forge_db.py
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch

@pytest.fixture
def tmp_db(tmp_path):
    db_path = tmp_path / "skill_forge_test.db"
    with patch("tools.skill_forge_db.SKILL_FORGE_DB_PATH", db_path):
        import tools.skill_forge_db as db
        db.init_db()
        yield db

def test_create_session(tmp_db):
    session_id = tmp_db.create_session_sync(
        task_spec={"task_name": "VC pitch deck", "domain": "venture capital"},
        current_stage="intent",
    )
    assert isinstance(session_id, int)
    assert session_id > 0

def test_update_session_stage(tmp_db):
    session_id = tmp_db.create_session_sync(
        task_spec={"task_name": "test"}, current_stage="intent"
    )
    tmp_db.update_session_stage_sync(session_id, "research")
    row = tmp_db.get_session_sync(session_id)
    assert row["current_stage"] == "research"

def test_save_and_get_research_bundle(tmp_db):
    session_id = tmp_db.create_session_sync(
        task_spec={"task_name": "test"}, current_stage="research"
    )
    tmp_db.save_research_bundle_sync(
        session_id=session_id,
        researcher_type="domain",
        findings={"key": "value"},
        citations=["source1"],
    )
    bundles = tmp_db.get_research_bundles_sync(session_id)
    assert len(bundles) == 1
    assert bundles[0]["researcher_type"] == "domain"

def test_save_skill_version(tmp_db):
    session_id = tmp_db.create_session_sync(
        task_spec={"task_name": "test"}, current_stage="draft"
    )
    tmp_db.save_skill_version_sync(
        session_id=session_id,
        version=0,
        skill_content="# SKILL.md content",
        composite_score=None,
        iteration_notes="initial draft",
    )
    versions = tmp_db.get_skill_versions_sync(session_id)
    assert len(versions) == 1
    assert versions[0]["version"] == 0

def test_save_battle_test_result(tmp_db):
    session_id = tmp_db.create_session_sync(
        task_spec={"task_name": "test"}, current_stage="redteam"
    )
    tmp_db.save_battle_test_result_sync(
        session_id=session_id,
        version=0,
        pass_rate=0.87,
        failure_breakdown={"common": 1, "edge": 3},
        worst_cases=["case1", "case2"],
    )
    results = tmp_db.get_battle_test_results_sync(session_id)
    assert len(results) == 1
    assert results[0]["pass_rate"] == pytest.approx(0.87)

def test_staging_registry(tmp_db):
    tmp_db.add_to_staging_sync(
        skill_id="vc-pitch-deck",
        skill_name="VC Pitch Deck Writer",
        department="generated",
        file_path="generated_skills/startup/vc-pitch-deck/SKILL.md",
        composite_score=8.7,
    )
    entry = tmp_db.get_staging_entry_sync("vc-pitch-deck")
    assert entry["composite_score"] == pytest.approx(8.7)
    assert entry["production_runs"] == 0

def test_increment_production_runs(tmp_db):
    tmp_db.add_to_staging_sync(
        skill_id="test-skill",
        skill_name="Test",
        department="generated",
        file_path="generated_skills/test/SKILL.md",
        composite_score=8.5,
    )
    tmp_db.increment_production_runs_sync("test-skill")
    tmp_db.increment_production_runs_sync("test-skill")
    entry = tmp_db.get_staging_entry_sync("test-skill")
    assert entry["production_runs"] == 2
```

- [ ] **Step 2: Run tests — confirm they fail**

```bash
cd aass_agents && python -m pytest tests/skill_forge/test_skill_forge_db.py -v
```
Expected: `ModuleNotFoundError: No module named 'tools.skill_forge_db'`

- [ ] **Step 3: Implement `skill_forge_db.py`**

```python
# aass_agents/tools/skill_forge_db.py
"""
Skill Forge DB — schema and CRUD for the autonomous skill generation pipeline.

Tables:
  forge_sessions       : one row per skill generation run, tracks current stage
  research_bundles     : output of the 3-agent research swarm
  skill_versions       : every SKILL.md version generated per session
  battle_test_results  : red team test results per version
  staging_registry     : skills awaiting production promotion

Mirrors evolution_db.py patterns: WAL mode, asyncio.to_thread, Row factory.
"""
import asyncio
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

SKILL_FORGE_DB_PATH = Path(__file__).parent.parent / "skill_forge.db"

DDL = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS forge_sessions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    task_spec     TEXT NOT NULL,
    current_stage TEXT NOT NULL,
    status        TEXT DEFAULT 'in_progress',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS research_bundles (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      INTEGER NOT NULL,
    researcher_type TEXT NOT NULL,
    findings        TEXT NOT NULL,
    citations       TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES forge_sessions(id)
);

CREATE TABLE IF NOT EXISTS skill_versions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id       INTEGER NOT NULL,
    version          INTEGER NOT NULL,
    skill_content    TEXT NOT NULL,
    composite_score  REAL,
    iteration_notes  TEXT,
    created_at       TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES forge_sessions(id)
);

CREATE TABLE IF NOT EXISTS battle_test_results (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id        INTEGER NOT NULL,
    version           INTEGER NOT NULL,
    pass_rate         REAL NOT NULL,
    failure_breakdown TEXT NOT NULL,
    worst_cases       TEXT NOT NULL,
    created_at        TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES forge_sessions(id)
);

CREATE TABLE IF NOT EXISTS staging_registry (
    skill_id         TEXT PRIMARY KEY,
    skill_name       TEXT NOT NULL,
    department       TEXT NOT NULL,
    file_path        TEXT NOT NULL,
    composite_score  REAL NOT NULL,
    production_runs  INTEGER DEFAULT 0,
    needs_review     INTEGER DEFAULT 0,
    promoted_at      TEXT,
    created_at       TEXT NOT NULL
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
    with _connect() as conn:
        conn.executescript(DDL)


# ── forge_sessions ─────────────────────────────────────────────────────────────

def create_session_sync(task_spec: dict, current_stage: str) -> int:
    now = _now_iso()
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO forge_sessions (task_spec, current_stage, status, created_at, updated_at) "
            "VALUES (?, ?, 'in_progress', ?, ?)",
            (json.dumps(task_spec), current_stage, now, now),
        )
        return cur.lastrowid


async def create_session(task_spec: dict, current_stage: str) -> int:
    return await asyncio.to_thread(create_session_sync, task_spec, current_stage)


def update_session_stage_sync(session_id: int, stage: str, status: str = "in_progress") -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE forge_sessions SET current_stage=?, status=?, updated_at=? WHERE id=?",
            (stage, status, _now_iso(), session_id),
        )


async def update_session_stage(session_id: int, stage: str, status: str = "in_progress") -> None:
    await asyncio.to_thread(update_session_stage_sync, session_id, stage, status)


def get_session_sync(session_id: int) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM forge_sessions WHERE id=?", (session_id,)
        ).fetchone()
    return dict(row) if row else None


async def get_session(session_id: int) -> Optional[dict]:
    return await asyncio.to_thread(get_session_sync, session_id)


# ── research_bundles ───────────────────────────────────────────────────────────

def save_research_bundle_sync(
    session_id: int,
    researcher_type: str,
    findings: dict,
    citations: list[str],
) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO research_bundles (session_id, researcher_type, findings, citations, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (session_id, researcher_type, json.dumps(findings), json.dumps(citations), _now_iso()),
        )


async def save_research_bundle(
    session_id: int, researcher_type: str, findings: dict, citations: list[str]
) -> None:
    await asyncio.to_thread(save_research_bundle_sync, session_id, researcher_type, findings, citations)


def get_research_bundles_sync(session_id: int) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM research_bundles WHERE session_id=? ORDER BY created_at",
            (session_id,),
        ).fetchall()
    result = []
    for row in rows:
        d = dict(row)
        d["findings"] = json.loads(d["findings"])
        d["citations"] = json.loads(d["citations"])
        result.append(d)
    return result


async def get_research_bundles(session_id: int) -> list[dict]:
    return await asyncio.to_thread(get_research_bundles_sync, session_id)


# ── skill_versions ─────────────────────────────────────────────────────────────

def save_skill_version_sync(
    session_id: int,
    version: int,
    skill_content: str,
    composite_score: Optional[float],
    iteration_notes: Optional[str],
) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO skill_versions "
            "(session_id, version, skill_content, composite_score, iteration_notes, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, version, skill_content, composite_score, iteration_notes, _now_iso()),
        )


async def save_skill_version(
    session_id: int, version: int, skill_content: str,
    composite_score: Optional[float], iteration_notes: Optional[str]
) -> None:
    await asyncio.to_thread(
        save_skill_version_sync, session_id, version, skill_content, composite_score, iteration_notes
    )


def get_skill_versions_sync(session_id: int) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM skill_versions WHERE session_id=? ORDER BY version",
            (session_id,),
        ).fetchall()
    return [dict(r) for r in rows]


async def get_skill_versions(session_id: int) -> list[dict]:
    return await asyncio.to_thread(get_skill_versions_sync, session_id)


def get_best_skill_version_sync(session_id: int) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM skill_versions WHERE session_id=? "
            "ORDER BY composite_score DESC NULLS LAST LIMIT 1",
            (session_id,),
        ).fetchone()
    return dict(row) if row else None


async def get_best_skill_version(session_id: int) -> Optional[dict]:
    return await asyncio.to_thread(get_best_skill_version_sync, session_id)


# ── battle_test_results ────────────────────────────────────────────────────────

def save_battle_test_result_sync(
    session_id: int,
    version: int,
    pass_rate: float,
    failure_breakdown: dict,
    worst_cases: list[str],
) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO battle_test_results "
            "(session_id, version, pass_rate, failure_breakdown, worst_cases, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, version, pass_rate,
             json.dumps(failure_breakdown), json.dumps(worst_cases), _now_iso()),
        )


async def save_battle_test_result(
    session_id: int, version: int, pass_rate: float,
    failure_breakdown: dict, worst_cases: list[str]
) -> None:
    await asyncio.to_thread(
        save_battle_test_result_sync, session_id, version, pass_rate, failure_breakdown, worst_cases
    )


def get_battle_test_results_sync(session_id: int) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM battle_test_results WHERE session_id=? ORDER BY version",
            (session_id,),
        ).fetchall()
    result = []
    for row in rows:
        d = dict(row)
        d["failure_breakdown"] = json.loads(d["failure_breakdown"])
        d["worst_cases"] = json.loads(d["worst_cases"])
        result.append(d)
    return result


async def get_battle_test_results(session_id: int) -> list[dict]:
    return await asyncio.to_thread(get_battle_test_results_sync, session_id)


# ── staging_registry ───────────────────────────────────────────────────────────

def add_to_staging_sync(
    skill_id: str,
    skill_name: str,
    department: str,
    file_path: str,
    composite_score: float,
    needs_review: bool = False,
) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO staging_registry "
            "(skill_id, skill_name, department, file_path, composite_score, "
            " production_runs, needs_review, promoted_at, created_at) "
            "VALUES (?, ?, ?, ?, ?, 0, ?, NULL, ?)",
            (skill_id, skill_name, department, file_path, composite_score,
             int(needs_review), _now_iso()),
        )


async def add_to_staging(
    skill_id: str, skill_name: str, department: str, file_path: str,
    composite_score: float, needs_review: bool = False
) -> None:
    await asyncio.to_thread(
        add_to_staging_sync, skill_id, skill_name, department, file_path,
        composite_score, needs_review
    )


def get_staging_entry_sync(skill_id: str) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM staging_registry WHERE skill_id=?", (skill_id,)
        ).fetchone()
    return dict(row) if row else None


async def get_staging_entry(skill_id: str) -> Optional[dict]:
    return await asyncio.to_thread(get_staging_entry_sync, skill_id)


def increment_production_runs_sync(skill_id: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE staging_registry SET production_runs = production_runs + 1 WHERE skill_id=?",
            (skill_id,),
        )


async def increment_production_runs(skill_id: str) -> None:
    await asyncio.to_thread(increment_production_runs_sync, skill_id)


def mark_promoted_sync(skill_id: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE staging_registry SET promoted_at=? WHERE skill_id=?",
            (_now_iso(), skill_id),
        )


async def mark_promoted(skill_id: str) -> None:
    await asyncio.to_thread(mark_promoted_sync, skill_id)


def get_all_staging_sync() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM staging_registry ORDER BY composite_score DESC"
        ).fetchall()
    return [dict(r) for r in rows]


async def get_all_staging() -> list[dict]:
    return await asyncio.to_thread(get_all_staging_sync)


# Init on import
init_db()
```

- [ ] **Step 4: Run tests — confirm they pass**

```bash
cd aass_agents && python -m pytest tests/skill_forge/test_skill_forge_db.py -v
```
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add aass_agents/tools/skill_forge_db.py aass_agents/tests/skill_forge/test_skill_forge_db.py
git commit -m "feat: add skill_forge_db — schema and CRUD for skill generation pipeline"
```

---

### Task 2: Data Models

**Files:**
- Create: `aass_agents/agents/skill_forge/__init__.py`
- Create: `aass_agents/agents/skill_forge/models.py`
- Create: `aass_agents/tests/skill_forge/test_models.py`

- [ ] **Step 1: Write failing tests**

```python
# aass_agents/tests/skill_forge/test_models.py
import pytest
from agents.skill_forge.models import (
    TaskSpec, ResearchBundle, ExpertBlueprint,
    CriticScore, BattleTestReport, CompositeScore,
)

def test_task_spec_immutable():
    spec = TaskSpec(
        task_name="VC pitch deck",
        domain="venture capital",
        skill_type="writing",
        success_definition="investor requests follow-up",
        scope_boundaries="seed/series A",
        existing_skill_path=None,
        department="generated",
        priority="high",
    )
    with pytest.raises(Exception):
        spec.task_name = "changed"  # frozen dataclass

def test_task_spec_slug():
    spec = TaskSpec(
        task_name="VC Pitch Deck Writing",
        domain="venture capital",
        skill_type="writing",
        success_definition="...",
        scope_boundaries="...",
        existing_skill_path=None,
        department="generated",
        priority="high",
    )
    assert spec.slug() == "vc-pitch-deck-writing"

def test_composite_score_formula():
    score = CompositeScore(
        correctness=9.0,
        robustness=8.0,
        clarity=8.5,
        domain_accuracy=9.0,
    )
    expected = 0.35 * 9.0 + 0.25 * 8.0 + 0.20 * 8.5 + 0.20 * 9.0
    assert score.composite() == pytest.approx(expected)

def test_composite_score_threshold():
    passing = CompositeScore(correctness=9.0, robustness=9.0, clarity=9.0, domain_accuracy=9.0)
    failing = CompositeScore(correctness=7.0, robustness=7.0, clarity=7.0, domain_accuracy=7.0)
    assert passing.passes_staging_gate() is True
    assert failing.passes_staging_gate() is False

def test_battle_test_report_ci():
    report = BattleTestReport(
        total_cases=100,
        passed=89,
        failure_breakdown={"common": 1, "edge": 5, "adversarial": 3, "regression": 2},
        worst_cases=["case1", "case2"],
    )
    assert report.pass_rate() == pytest.approx(0.89)
    lower, upper = report.confidence_interval_95()
    assert lower < 0.89 < upper
    assert report.passes_confidence_gate() is True  # lower >= 0.80

def test_battle_test_report_fails_gate():
    report = BattleTestReport(
        total_cases=100,
        passed=75,
        failure_breakdown={},
        worst_cases=[],
    )
    assert report.passes_confidence_gate() is False
```

- [ ] **Step 2: Run tests — confirm they fail**

```bash
cd aass_agents && python -m pytest tests/skill_forge/test_models.py -v
```
Expected: `ModuleNotFoundError: No module named 'agents.skill_forge.models'`

- [ ] **Step 3: Implement models**

```python
# aass_agents/agents/skill_forge/__init__.py
# intentionally empty
```

```python
# aass_agents/agents/skill_forge/models.py
"""Immutable data transfer objects for the SKILL FORGE pipeline."""
import math
import re
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class TaskSpec:
    task_name: str
    domain: str
    skill_type: str          # writing | research | analysis | coding | strategy
    success_definition: str
    scope_boundaries: str
    existing_skill_path: Optional[str]
    department: str
    priority: str            # high | medium | low

    def slug(self) -> str:
        return re.sub(r"[^a-z0-9]+", "-", self.task_name.lower()).strip("-")


@dataclass(frozen=True)
class ResearchBundle:
    session_id: int
    researcher_type: str     # domain | benchmark | technique
    findings: dict
    citations: list[str]


@dataclass(frozen=True)
class ExpertBlueprint:
    constitutional_principles: list[str]   # 5-8 positive behavior-based rules
    gold_examples: list[dict]              # {"input": ..., "output": ...}
    failure_mode_catalog: list[str]        # known failure patterns
    success_criteria: list[str]            # measurable quality gates
    domain_constraints: list[str]          # things skill must never do


@dataclass(frozen=True)
class CriticScore:
    critic_type: str          # domain_expert | instruction_quality | edge_case
    score: float              # 1-10
    reasoning: str
    corrections: list[str]


@dataclass(frozen=True)
class CompositeScore:
    correctness: float
    robustness: float
    clarity: float
    domain_accuracy: float

    STAGING_THRESHOLD: float = 8.5
    CRITIQUE_THRESHOLD: float = 7.5

    def composite(self) -> float:
        return (
            0.35 * self.correctness
            + 0.25 * self.robustness
            + 0.20 * self.clarity
            + 0.20 * self.domain_accuracy
        )

    def passes_staging_gate(self) -> bool:
        return self.composite() >= self.STAGING_THRESHOLD

    def passes_critique_gate(self) -> bool:
        return self.composite() >= self.CRITIQUE_THRESHOLD


@dataclass(frozen=True)
class BattleTestReport:
    total_cases: int
    passed: int
    failure_breakdown: dict    # {"common": N, "edge": N, "adversarial": N, "regression": N}
    worst_cases: list[str]

    CI_GATE: float = 0.80      # lower bound of 95% CI must be >= this

    def pass_rate(self) -> float:
        return self.passed / self.total_cases

    def confidence_interval_95(self) -> tuple[float, float]:
        p = self.pass_rate()
        n = self.total_cases
        margin = 1.96 * math.sqrt(p * (1 - p) / n)
        return max(0.0, p - margin), min(1.0, p + margin)

    def passes_confidence_gate(self) -> bool:
        lower, _ = self.confidence_interval_95()
        return lower >= self.CI_GATE
```

- [ ] **Step 4: Run tests — confirm they pass**

```bash
cd aass_agents && python -m pytest tests/skill_forge/test_models.py -v
```
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add aass_agents/agents/skill_forge/ aass_agents/tests/skill_forge/test_models.py
git commit -m "feat: add skill_forge data models — TaskSpec, CompositeScore, BattleTestReport"
```

---

## Phase 2: Research Pipeline

### Task 3: Intent Parser Agent

**Files:**
- Create: `aass_agents/agents/skill_forge/intent_parser_agent.py`
- Create: `aass_agents/tests/skill_forge/test_intent_parser.py`

- [ ] **Step 1: Write failing tests**

```python
# aass_agents/tests/skill_forge/test_intent_parser.py
import pytest
from unittest.mock import patch, MagicMock
from agents.skill_forge.intent_parser_agent import parse_task_spec, make_intent_parser_agent

def test_parse_simple_request():
    raw = "generate skill for: writing VC pitch decks"
    spec = parse_task_spec(raw)
    assert spec.task_name != ""
    assert spec.domain != ""
    assert spec.skill_type in {"writing", "research", "analysis", "coding", "strategy"}
    assert spec.priority in {"high", "medium", "low"}
    assert spec.department == "generated"

def test_slug_is_url_safe():
    raw = "generate skill for: writing VC pitch decks"
    spec = parse_task_spec(raw)
    import re
    assert re.match(r"^[a-z0-9-]+$", spec.slug())

def test_make_agent_returns_agent():
    from google.adk.agents import Agent
    agent = make_intent_parser_agent()
    assert isinstance(agent, Agent)
    assert agent.name == "intent_parser_agent"

def test_detect_existing_skill_upgrade(tmp_path):
    raw = "upgrade the lead-research skill to also handle LinkedIn outreach"
    spec = parse_task_spec(raw)
    # Should not crash; task_name should be non-empty
    assert spec.task_name != ""
```

- [ ] **Step 2: Run — confirm fail**

```bash
cd aass_agents && python -m pytest tests/skill_forge/test_intent_parser.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# aass_agents/agents/skill_forge/intent_parser_agent.py
"""
Intent Parser Agent — converts raw NLP input into a structured TaskSpec.

Parses: task name, domain, skill type, success definition, scope, department.
Asks at most ONE clarifying question if the domain or success_definition is ambiguous.
"""
import json
import os
import re
from typing import Optional

from google.adk.agents import Agent

from agents.skill_forge.models import TaskSpec

MODEL = os.getenv("MODEL_ID", "gemini-2.0-flash")

INSTRUCTION = """
You are the Intent Parser for SKILL FORGE. Convert a natural language skill request
into a structured JSON TaskSpec. Never ask more than one clarifying question.

## Output Format

Return ONLY valid JSON matching this schema:
{
  "task_name": "short human-readable name (3-6 words)",
  "domain": "specific domain (e.g. 'venture capital fundraising')",
  "skill_type": "writing | research | analysis | coding | strategy",
  "success_definition": "one sentence: what does success look like for a human doing this task?",
  "scope_boundaries": "what is in scope and out of scope",
  "existing_skill_path": null or "path/to/existing/SKILL.md if upgrading",
  "department": "generated",
  "priority": "high | medium | low"
}

## Rules

- skill_type: choose the PRIMARY type. Writing = producing text output. Research = gathering/synthesizing information. Analysis = evaluating/scoring/comparing. Coding = producing code. Strategy = planning/deciding.
- success_definition: make it concrete and human-observable, not vague ("investor books a follow-up meeting" not "good pitch deck")
- priority: default to "high" unless user specifies otherwise
- department: always "generated" for new skills
- If the request mentions upgrading/improving an existing skill, set existing_skill_path to the likely path under aass_agents/skills/

Return ONLY the JSON object, no markdown fences, no explanation.
"""


def parse_task_spec(raw_request: str) -> TaskSpec:
    """Synchronous parse for testing — uses a simple heuristic extraction.
    In production, this is called by the ADK agent which uses the LLM."""
    # Heuristic extraction for testing without LLM
    task_name = raw_request
    for prefix in ["generate skill for:", "create a skill that", "build me a skill to",
                    "forge skill:", "upgrade the", "improve the"]:
        if prefix in raw_request.lower():
            task_name = raw_request.lower().split(prefix)[-1].strip()
            break

    task_name = task_name.strip().title()[:60]

    # Infer skill_type from keywords
    writing_kw = {"write", "writing", "draft", "compose", "pitch", "email", "letter", "report"}
    coding_kw = {"code", "coding", "implement", "build", "develop", "script"}
    research_kw = {"research", "find", "gather", "analyze", "competitive", "market"}
    analysis_kw = {"analyze", "evaluate", "score", "compare", "audit", "review"}

    lower = raw_request.lower()
    if any(k in lower for k in coding_kw):
        skill_type = "coding"
    elif any(k in lower for k in research_kw):
        skill_type = "research"
    elif any(k in lower for k in analysis_kw):
        skill_type = "analysis"
    elif any(k in lower for k in writing_kw):
        skill_type = "writing"
    else:
        skill_type = "strategy"

    return TaskSpec(
        task_name=task_name,
        domain=task_name,
        skill_type=skill_type,
        success_definition=f"Human expert successfully completes: {task_name}",
        scope_boundaries="Standard use cases for this task type",
        existing_skill_path=None,
        department="generated",
        priority="high",
    )


def make_intent_parser_agent() -> Agent:
    return Agent(
        model=MODEL,
        name="intent_parser_agent",
        description=(
            "Converts a natural language skill generation request into a structured TaskSpec. "
            "Call with the raw NLP input. Returns JSON with task_name, domain, skill_type, "
            "success_definition, scope_boundaries, department, and priority."
        ),
        instruction=INSTRUCTION,
        tools=[],
    )


intent_parser_agent = make_intent_parser_agent()
```

- [ ] **Step 4: Run — confirm pass**

```bash
cd aass_agents && python -m pytest tests/skill_forge/test_intent_parser.py -v
```
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add aass_agents/agents/skill_forge/intent_parser_agent.py \
        aass_agents/tests/skill_forge/test_intent_parser.py
git commit -m "feat: add intent_parser_agent — NLP → TaskSpec conversion"
```

---

### Task 4: Research Swarm Agent

**Files:**
- Create: `aass_agents/agents/skill_forge/research_swarm_agent.py`
- Create: `aass_agents/tests/skill_forge/test_research_swarm.py`

- [ ] **Step 1: Write failing tests**

```python
# aass_agents/tests/skill_forge/test_research_swarm.py
import pytest
from agents.skill_forge.research_swarm_agent import (
    make_domain_researcher,
    make_benchmark_researcher,
    make_technique_researcher,
    build_research_prompt,
)
from agents.skill_forge.models import TaskSpec
from google.adk.agents import Agent


@pytest.fixture
def sample_spec():
    return TaskSpec(
        task_name="VC Pitch Deck Writing",
        domain="venture capital fundraising",
        skill_type="writing",
        success_definition="investor requests follow-up meeting",
        scope_boundaries="seed/series A, B2B SaaS",
        existing_skill_path=None,
        department="generated",
        priority="high",
    )


def test_make_domain_researcher_returns_agent(sample_spec):
    agent = make_domain_researcher(sample_spec)
    assert isinstance(agent, Agent)
    assert agent.name == "domain_researcher"


def test_make_benchmark_researcher_returns_agent(sample_spec):
    agent = make_benchmark_researcher(sample_spec)
    assert isinstance(agent, Agent)
    assert agent.name == "benchmark_researcher"


def test_make_technique_researcher_returns_agent(sample_spec):
    agent = make_technique_researcher(sample_spec)
    assert isinstance(agent, Agent)
    assert agent.name == "technique_researcher"


def test_build_research_prompt_contains_domain(sample_spec):
    prompt = build_research_prompt(sample_spec, "domain")
    assert "venture capital fundraising" in prompt
    assert "VC Pitch Deck Writing" in prompt


def test_build_research_prompt_type_specific(sample_spec):
    domain_prompt = build_research_prompt(sample_spec, "domain")
    benchmark_prompt = build_research_prompt(sample_spec, "benchmark")
    technique_prompt = build_research_prompt(sample_spec, "technique")
    # Each prompt should have type-specific content
    assert "expert" in domain_prompt.lower()
    assert "top 1%" in benchmark_prompt.lower() or "gold standard" in benchmark_prompt.lower()
    assert "technique" in technique_prompt.lower() or "method" in technique_prompt.lower()
```

- [ ] **Step 2: Run — confirm fail**

```bash
cd aass_agents && python -m pytest tests/skill_forge/test_research_swarm.py -v
```

- [ ] **Step 3: Implement**

```python
# aass_agents/agents/skill_forge/research_swarm_agent.py
"""
Research Swarm — three specialized researchers that run in parallel.

- domain_researcher:    What do human experts know and do in this domain?
- benchmark_researcher: What does top 1% performance look like concretely?
- technique_researcher: What tools/frameworks/prompting patterns help this task?

Each agent returns a ResearchBundle as structured JSON.
"""
import os
from google.adk.agents import Agent
from agents.skill_forge.models import TaskSpec

MODEL = os.getenv("MODEL_ID", "gemini-2.0-flash")

_SHARED_OUTPUT_FORMAT = """
## Output Format

Return ONLY valid JSON:
{
  "key_findings": [
    {"finding": "...", "evidence": "...", "source": "..."},
    ...
  ],
  "citations": ["source1", "source2", ...],
  "confidence": "high | medium | low",
  "gaps": ["what you could not find"]
}

Return at least 5 key_findings. Be specific — no generic observations.
"""

_DOMAIN_INSTRUCTION = """
You are a Domain Research Specialist for SKILL FORGE. Your task: deeply research
what human EXPERTS in a given domain know, think, and do when performing a task.

## Research Focus
- Expert mental models: how do top practitioners frame this problem?
- Decision heuristics: what rules-of-thumb do experts use?
- Common mistakes: what separates novices from experts?
- Best practices: what does current professional consensus recommend?
- Edge cases experts handle that novices miss

## Sources to Prioritize
1. Published expert practitioners (books, keynotes, interviews)
2. Academic research on expert performance in this domain
3. Professional community standards and certifications
4. Case studies showing expert vs. novice outcomes

""" + _SHARED_OUTPUT_FORMAT

_BENCHMARK_INSTRUCTION = """
You are a Benchmark Research Specialist for SKILL FORGE. Your task: find concrete
evidence of what TOP 1% human performance looks like on a given task.

## Research Focus
- Gold standard outputs: what does an exceptional result actually look like?
- Measurable quality criteria: how do judges/evaluators score this task?
- Human baseline data: what do average humans score? What do experts score?
- Competition results: leaderboards, contests, benchmarks for this task
- Before/after examples: novice output vs. expert output on the same input

## Sources to Prioritize
1. Competition entries and judging rubrics
2. Published evaluation frameworks for this domain
3. Academic studies measuring human performance
4. Professional certification scoring guides

""" + _SHARED_OUTPUT_FORMAT

_TECHNIQUE_INSTRUCTION = """
You are a Technique Research Specialist for SKILL FORGE. Your task: find the best
tools, frameworks, prompting patterns, and structured methods for performing a task.

## Research Focus
- Structured methodologies: step-by-step frameworks experts follow
- Prompting patterns: Chain-of-Thought, role-anchoring, or domain-specific techniques
- Tool integrations: software, APIs, or resources that enhance performance
- Recent advances: techniques from 2024-2026 that improve outcomes
- Existing Claude Code skills: similar SKILL.md files to learn from

## Sources to Prioritize
1. Practitioner guides and playbooks
2. Academic papers on task-specific techniques
3. Tool documentation and best practices
4. Engineering blogs with production lessons

""" + _SHARED_OUTPUT_FORMAT


def build_research_prompt(spec: TaskSpec, researcher_type: str) -> str:
    type_context = {
        "domain": f"Research expert knowledge and best practices for: {spec.task_name}\nDomain: {spec.domain}\nSuccess looks like: {spec.success_definition}",
        "benchmark": f"Find top 1% gold standard outputs and performance benchmarks for: {spec.task_name}\nDomain: {spec.domain}\nSuccess looks like: {spec.success_definition}",
        "technique": f"Find best tools, frameworks, and techniques for: {spec.task_name}\nDomain: {spec.domain}\nSkill type: {spec.skill_type}",
    }
    return type_context[researcher_type]


def make_domain_researcher(spec: TaskSpec) -> Agent:
    return Agent(
        model=MODEL,
        name="domain_researcher",
        description=(
            f"Researches expert domain knowledge for: {spec.task_name}. "
            "Returns findings on expert mental models, heuristics, best practices."
        ),
        instruction=_DOMAIN_INSTRUCTION + f"\n\n## Your Research Target\n{build_research_prompt(spec, 'domain')}",
        tools=[],
    )


def make_benchmark_researcher(spec: TaskSpec) -> Agent:
    return Agent(
        model=MODEL,
        name="benchmark_researcher",
        description=(
            f"Researches top 1% performance benchmarks for: {spec.task_name}. "
            "Returns gold standard outputs, scoring rubrics, human baselines."
        ),
        instruction=_BENCHMARK_INSTRUCTION + f"\n\n## Your Research Target\n{build_research_prompt(spec, 'benchmark')}",
        tools=[],
    )


def make_technique_researcher(spec: TaskSpec) -> Agent:
    return Agent(
        model=MODEL,
        name="technique_researcher",
        description=(
            f"Researches tools, frameworks, and techniques for: {spec.task_name}. "
            "Returns structured methodologies and prompting patterns."
        ),
        instruction=_TECHNIQUE_INSTRUCTION + f"\n\n## Your Research Target\n{build_research_prompt(spec, 'technique')}",
        tools=[],
    )
```

- [ ] **Step 4: Run — confirm pass**

```bash
cd aass_agents && python -m pytest tests/skill_forge/test_research_swarm.py -v
```
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add aass_agents/agents/skill_forge/research_swarm_agent.py \
        aass_agents/tests/skill_forge/test_research_swarm.py
git commit -m "feat: add research_swarm_agent — 3 parallel domain/benchmark/technique researchers"
```

---

### Task 5: Expert Synthesizer Agent

**Files:**
- Create: `aass_agents/agents/skill_forge/expert_synthesizer_agent.py`
- Create: `aass_agents/tests/skill_forge/test_expert_synthesizer.py`

- [ ] **Step 1: Write failing tests**

```python
# aass_agents/tests/skill_forge/test_expert_synthesizer.py
import pytest
from agents.skill_forge.expert_synthesizer_agent import (
    make_expert_synthesizer_agent,
    build_synthesis_prompt,
)
from agents.skill_forge.models import TaskSpec, ResearchBundle, ExpertBlueprint
from google.adk.agents import Agent


@pytest.fixture
def sample_bundles():
    return [
        ResearchBundle(
            session_id=1,
            researcher_type="domain",
            findings={"key_findings": [{"finding": "Experts open with problem clarity", "evidence": "McKinsey decks", "source": "HBR"}]},
            citations=["HBR 2024"],
        ),
        ResearchBundle(
            session_id=1,
            researcher_type="benchmark",
            findings={"key_findings": [{"finding": "Top decks have exactly 10 slides", "evidence": "YC data", "source": "YC"}]},
            citations=["YC Blog 2025"],
        ),
        ResearchBundle(
            session_id=1,
            researcher_type="technique",
            findings={"key_findings": [{"finding": "Problem-Solution-Market-Team-Ask structure wins", "evidence": "500+ decks analyzed", "source": "DocSend"}]},
            citations=["DocSend Report 2024"],
        ),
    ]


def test_make_expert_synthesizer_returns_agent():
    agent = make_expert_synthesizer_agent()
    assert isinstance(agent, Agent)
    assert agent.name == "expert_synthesizer_agent"


def test_build_synthesis_prompt_includes_all_bundles(sample_bundles):
    prompt = build_synthesis_prompt(sample_bundles)
    assert "domain" in prompt
    assert "benchmark" in prompt
    assert "technique" in prompt
    assert "Experts open with problem clarity" in prompt


def test_build_synthesis_prompt_requests_blueprint_format(sample_bundles):
    prompt = build_synthesis_prompt(sample_bundles)
    assert "constitutional_principles" in prompt
    assert "gold_examples" in prompt
    assert "failure_mode_catalog" in prompt
```

- [ ] **Step 2: Run — confirm fail**

```bash
cd aass_agents && python -m pytest tests/skill_forge/test_expert_synthesizer.py -v
```

- [ ] **Step 3: Implement**

```python
# aass_agents/agents/skill_forge/expert_synthesizer_agent.py
"""
Expert Synthesizer Agent — distills 3 ResearchBundles into an ExpertBlueprint.

Applies Constitutional AI synthesis: extracts positive, behavior-based principles
from cross-source expert consensus. Output feeds directly into Skill Drafter.
"""
import json
import os
from google.adk.agents import Agent
from agents.skill_forge.models import ResearchBundle

MODEL = os.getenv("MODEL_ID", "gemini-2.0-flash")

INSTRUCTION = """
You are the Expert Synthesizer for SKILL FORGE. You receive research findings from
3 specialist researchers (domain, benchmark, technique) and synthesize them into
an ExpertBlueprint — the structured knowledge base that powers skill generation.

## Constitutional AI Synthesis Rules

1. Extract POSITIVE principles: frame as "do X" not "avoid Y"
   - Wrong: "Don't use vague language"
   - Right: "Use specific, concrete language with evidence for every claim"

2. Principles must be BEHAVIOR-BASED: describe observable actions, not attitudes
   - Wrong: "Be thorough"
   - Right: "Cover all 5 required sections before concluding"

3. Cross-validate across all 3 research sources: only include findings supported
   by at least 2 of the 3 researchers, OR findings unique to 1 researcher that are
   so specific and well-evidenced they cannot be ignored

4. Gold examples must be CONCRETE: actual input/output pairs, not descriptions

## Output Format

Return ONLY valid JSON:
{
  "constitutional_principles": [
    "Principle 1 (positive, behavior-based, 1-2 sentences)",
    "Principle 2",
    ...
  ],
  "gold_examples": [
    {
      "label": "Strong example",
      "input": "specific input scenario",
      "output": "what excellent output looks like",
      "why_excellent": "what makes this top 1%"
    },
    ...
  ],
  "failure_mode_catalog": [
    "Failure mode 1: [what happens] [why it fails] [how to spot it]",
    ...
  ],
  "success_criteria": [
    "Measurable criterion 1 (binary pass/fail)",
    ...
  ],
  "domain_constraints": [
    "Constraint 1: never do X because Y",
    ...
  ]
}

Requirements:
- 5-8 constitutional_principles
- 3-5 gold_examples
- 5-10 failure_mode_catalog entries
- 3-6 success_criteria (all must be testable, binary pass/fail)
- 2-5 domain_constraints
"""


def build_synthesis_prompt(bundles: list[ResearchBundle]) -> str:
    sections = []
    for bundle in bundles:
        findings_text = json.dumps(bundle.findings, indent=2)
        sections.append(
            f"## {bundle.researcher_type.upper()} RESEARCH\n"
            f"Citations: {', '.join(bundle.citations)}\n\n"
            f"{findings_text}"
        )
    return "\n\n".join(sections) + "\n\nSynthesize the above into an ExpertBlueprint JSON with fields: constitutional_principles, gold_examples, failure_mode_catalog, success_criteria, domain_constraints."


def make_expert_synthesizer_agent() -> Agent:
    return Agent(
        model=MODEL,
        name="expert_synthesizer_agent",
        description=(
            "Synthesizes 3 ResearchBundles (domain, benchmark, technique) into an "
            "ExpertBlueprint using Constitutional AI principles. Returns JSON with "
            "constitutional_principles, gold_examples, failure_mode_catalog, "
            "success_criteria, domain_constraints."
        ),
        instruction=INSTRUCTION,
        tools=[],
    )


expert_synthesizer_agent = make_expert_synthesizer_agent()
```

- [ ] **Step 4: Run — confirm pass**

```bash
cd aass_agents && python -m pytest tests/skill_forge/test_expert_synthesizer.py -v
```

- [ ] **Step 5: Commit**

```bash
git add aass_agents/agents/skill_forge/expert_synthesizer_agent.py \
        aass_agents/tests/skill_forge/test_expert_synthesizer.py
git commit -m "feat: add expert_synthesizer_agent — Constitutional AI synthesis of research bundles"
```

---

## Phase 3: Generation Pipeline

### Task 6: Skill Drafter Agent

**Files:**
- Create: `aass_agents/agents/skill_forge/skill_drafter_agent.py`
- Create: `aass_agents/tests/skill_forge/test_skill_drafter.py`

- [ ] **Step 1: Write failing tests**

```python
# aass_agents/tests/skill_forge/test_skill_drafter.py
import pytest
from agents.skill_forge.skill_drafter_agent import (
    make_skill_drafter_agent,
    build_draft_prompt,
    validate_skill_md_structure,
)
from agents.skill_forge.models import TaskSpec, ExpertBlueprint
from google.adk.agents import Agent


@pytest.fixture
def sample_spec():
    return TaskSpec(
        task_name="VC Pitch Deck Writing",
        domain="venture capital fundraising",
        skill_type="writing",
        success_definition="investor requests follow-up meeting",
        scope_boundaries="seed/series A",
        existing_skill_path=None,
        department="generated",
        priority="high",
    )


@pytest.fixture
def sample_blueprint():
    return ExpertBlueprint(
        constitutional_principles=["Use specific evidence for every claim"],
        gold_examples=[{"label": "Strong", "input": "...", "output": "...", "why_excellent": "..."}],
        failure_mode_catalog=["Vague market sizing without data"],
        success_criteria=["All 5 required sections present"],
        domain_constraints=["Never fabricate traction metrics"],
    )


def test_make_skill_drafter_returns_agent(sample_spec, sample_blueprint):
    agent = make_skill_drafter_agent(sample_spec, sample_blueprint)
    assert isinstance(agent, Agent)
    assert agent.name == "skill_drafter_agent"


def test_build_draft_prompt_contains_principles(sample_spec, sample_blueprint):
    prompt = build_draft_prompt(sample_spec, sample_blueprint)
    assert "Use specific evidence for every claim" in prompt
    assert "VC Pitch Deck Writing" in prompt


def test_validate_skill_md_structure_passes():
    valid_skill = """---
name: vc-pitch-deck-writing
description: >
  A skill for writing VC pitch decks.
---

# VC Pitch Deck Writing

## Instructions

### Step 1: Do the thing

- [ ] Action here
"""
    errors = validate_skill_md_structure(valid_skill)
    assert errors == []


def test_validate_skill_md_structure_catches_missing_frontmatter():
    invalid_skill = "# Just a title\n\nNo frontmatter here."
    errors = validate_skill_md_structure(invalid_skill)
    assert len(errors) > 0
    assert any("frontmatter" in e.lower() for e in errors)


def test_validate_skill_md_structure_catches_missing_instructions():
    invalid_skill = """---
name: test
description: test
---

# Test Skill

No instructions section here.
"""
    errors = validate_skill_md_structure(invalid_skill)
    assert any("instructions" in e.lower() for e in errors)
```

- [ ] **Step 2: Run — confirm fail**

```bash
cd aass_agents && python -m pytest tests/skill_forge/test_skill_drafter.py -v
```

- [ ] **Step 3: Implement**

```python
# aass_agents/agents/skill_forge/skill_drafter_agent.py
"""
Skill Drafter Agent — generates SKILL.md v0 from TaskSpec + ExpertBlueprint.

Uses DSPy-inspired pattern: instruction text is derived from constitutional
principles, demos selected from gold_examples, failure guards from catalog.
Output is a complete SKILL.md following the aass_agents/skills/ format.
"""
import os
import re
from google.adk.agents import Agent
from agents.skill_forge.models import TaskSpec, ExpertBlueprint

MODEL = os.getenv("MODEL_ID", "gemini-2.0-flash")

_SKILL_MD_FORMAT = """
## Required SKILL.md Format

```
---
name: {slug}
description: >
  One-line description of what this skill does and when to invoke it.
  Include trigger phrases.
---

# {task_name}

You are a {domain} specialist. [Role statement anchoring the skill.]

## Instructions

### Step 1: [First major action]

[Detailed instructions for this step, grounded in expert knowledge]

### Step 2: [Second major action]

[Continue...]

## Quality Checklist

Before completing, verify:
- [ ] [Criterion 1 — binary pass/fail]
- [ ] [Criterion 2]

## Examples

### Example 1: [Label]

**Input:** [Specific input]
**Output:** [What excellent output looks like]
**Why this is top 1%:** [What makes this exceptional]

## Common Failures to Avoid

- **[Failure mode 1]:** [What it is] [How to avoid it]
- **[Failure mode 2]:** [What it is] [How to avoid it]
```
"""

INSTRUCTION = """
You are the Skill Drafter for SKILL FORGE. Generate a complete, production-ready
SKILL.md file from the provided TaskSpec and ExpertBlueprint.

## Drafting Rules

1. Every instruction step must be SPECIFIC and ACTIONABLE — never "be thorough" or "consider X"
2. Embed constitutional principles as explicit instructions, not just guidelines
3. Include 2-3 gold examples from the ExpertBlueprint (input + output + why excellent)
4. Add failure guards: "If you see X, do Y instead of Z"
5. Use Focused Chain-of-Thought: for complex steps, structure as "First extract... then reason... then conclude..."
6. Role-anchor the skill: start with "You are a [specific expert role]"
7. Quality checklist must be binary pass/fail — no subjective criteria
8. Keep instructions scannable: use numbered steps, sub-bullets, bold key terms

## Output

Return the complete SKILL.md content as a plain text string (no JSON wrapper).
Start with --- (frontmatter), end after the last content section.
""" + _SKILL_MD_FORMAT


def build_draft_prompt(spec: TaskSpec, blueprint: ExpertBlueprint) -> str:
    principles = "\n".join(f"- {p}" for p in blueprint.constitutional_principles)
    failures = "\n".join(f"- {f}" for f in blueprint.failure_mode_catalog)
    criteria = "\n".join(f"- {c}" for c in blueprint.success_criteria)
    constraints = "\n".join(f"- {c}" for c in blueprint.domain_constraints)

    examples_text = ""
    for i, ex in enumerate(blueprint.gold_examples[:3], 1):
        examples_text += f"\nExample {i} ({ex.get('label', 'Strong')}):\n"
        examples_text += f"  Input: {ex.get('input', '')}\n"
        examples_text += f"  Output: {ex.get('output', '')}\n"
        examples_text += f"  Why excellent: {ex.get('why_excellent', '')}\n"

    return (
        f"## Task to Skill\n"
        f"Task name: {spec.task_name}\n"
        f"Domain: {spec.domain}\n"
        f"Skill type: {spec.skill_type}\n"
        f"Success definition: {spec.success_definition}\n"
        f"Scope: {spec.scope_boundaries}\n\n"
        f"## Constitutional Principles (embed these as instructions)\n{principles}\n\n"
        f"## Gold Examples (include 2-3 of these)\n{examples_text}\n"
        f"## Failure Modes (add guards for these)\n{failures}\n\n"
        f"## Success Criteria (use for quality checklist)\n{criteria}\n\n"
        f"## Domain Constraints (these are hard rules)\n{constraints}\n\n"
        f"Generate the complete SKILL.md now."
    )


def validate_skill_md_structure(skill_content: str) -> list[str]:
    """Returns list of structural errors. Empty list = valid."""
    errors = []
    if not skill_content.strip().startswith("---"):
        errors.append("Missing YAML frontmatter (must start with ---)")
    if "name:" not in skill_content:
        errors.append("Frontmatter missing 'name:' field")
    if "description:" not in skill_content:
        errors.append("Frontmatter missing 'description:' field")
    if "## Instructions" not in skill_content and "## Instructions" not in skill_content:
        if "### Step" not in skill_content:
            errors.append("Missing Instructions section (need ## Instructions or ### Step headers)")
    if "- [ ]" not in skill_content:
        errors.append("Missing checklist items (quality checklist must use - [ ] syntax)")
    return errors


def make_skill_drafter_agent(spec: TaskSpec, blueprint: ExpertBlueprint) -> Agent:
    return Agent(
        model=MODEL,
        name="skill_drafter_agent",
        description=(
            f"Generates a complete SKILL.md for: {spec.task_name}. "
            "Uses constitutional principles, gold examples, and failure guards "
            "from ExpertBlueprint to produce a production-ready skill."
        ),
        instruction=INSTRUCTION + f"\n\n## Your Drafting Input\n{build_draft_prompt(spec, blueprint)}",
        tools=[],
    )
```

- [ ] **Step 4: Run — confirm pass**

```bash
cd aass_agents && python -m pytest tests/skill_forge/test_skill_drafter.py -v
```

- [ ] **Step 5: Commit**

```bash
git add aass_agents/agents/skill_forge/skill_drafter_agent.py \
        aass_agents/tests/skill_forge/test_skill_drafter.py
git commit -m "feat: add skill_drafter_agent — DSPy-style SKILL.md generation from ExpertBlueprint"
```

---

### Task 7: Critic Panel Agent

**Files:**
- Create: `aass_agents/agents/skill_forge/critic_panel_agent.py`
- Create: `aass_agents/tests/skill_forge/test_critic_panel.py`

- [ ] **Step 1: Write failing tests**

```python
# aass_agents/tests/skill_forge/test_critic_panel.py
import pytest
from agents.skill_forge.critic_panel_agent import (
    make_domain_expert_critic,
    make_instruction_quality_critic,
    make_edge_case_critic,
    compute_panel_composite,
    should_trigger_debate,
)
from agents.skill_forge.models import CriticScore, CompositeScore
from google.adk.agents import Agent


def test_make_critics_return_agents():
    skill_content = "# Test Skill\n\n## Instructions\n\n### Step 1\n- [ ] Do thing"
    domain = "venture capital"
    assert isinstance(make_domain_expert_critic(skill_content, domain), Agent)
    assert isinstance(make_instruction_quality_critic(skill_content), Agent)
    assert isinstance(make_edge_case_critic(skill_content, domain), Agent)


def test_compute_panel_composite():
    scores = [
        CriticScore(critic_type="domain_expert", score=9.0, reasoning="good", corrections=[]),
        CriticScore(critic_type="instruction_quality", score=8.0, reasoning="ok", corrections=[]),
        CriticScore(critic_type="edge_case", score=7.5, reasoning="some gaps", corrections=["fix X"]),
    ]
    composite = compute_panel_composite(scores)
    # All three critics contribute equally to panel score (simple average)
    assert composite == pytest.approx((9.0 + 8.0 + 7.5) / 3)


def test_should_trigger_debate_when_diverged():
    scores = [
        CriticScore(critic_type="domain_expert", score=9.0, reasoning="great", corrections=[]),
        CriticScore(critic_type="instruction_quality", score=6.0, reasoning="poor", corrections=["fix"]),
        CriticScore(critic_type="edge_case", score=8.5, reasoning="ok", corrections=[]),
    ]
    # Max divergence: 9.0 - 6.0 = 3.0 > 2.0 threshold
    assert should_trigger_debate(scores) is True


def test_should_not_trigger_debate_when_close():
    scores = [
        CriticScore(critic_type="domain_expert", score=8.0, reasoning="good", corrections=[]),
        CriticScore(critic_type="instruction_quality", score=8.5, reasoning="good", corrections=[]),
        CriticScore(critic_type="edge_case", score=7.8, reasoning="good", corrections=[]),
    ]
    # Max divergence: 8.5 - 7.8 = 0.7 < 2.0
    assert should_trigger_debate(scores) is False
```

- [ ] **Step 2: Run — confirm fail**

```bash
cd aass_agents && python -m pytest tests/skill_forge/test_critic_panel.py -v
```

- [ ] **Step 3: Implement**

```python
# aass_agents/agents/skill_forge/critic_panel_agent.py
"""
Critic Panel — three heterogeneous A-HMAD judges that debate skill quality.

- domain_expert_critic:      Is every claim factually correct for the domain?
- instruction_quality_critic: Can someone execute this without ambiguity?
- edge_case_critic:          What inputs will make this skill fail?

If any two critics diverge by >2 points: one debate round, then re-score.
Composite < 7.5 → back to Skill Drafter with critique notes.
"""
import os
from google.adk.agents import Agent
from agents.skill_forge.models import CriticScore

MODEL = os.getenv("MODEL_ID", "gemini-2.0-flash")

_CRITIC_OUTPUT_FORMAT = """
## Output Format

Return ONLY valid JSON:
{
  "score": 8.5,
  "reasoning": "2-3 sentence explanation of the score",
  "corrections": [
    "Specific correction 1: [what to change and why]",
    "Specific correction 2: ..."
  ],
  "passed_checks": ["list of things that are good and should be preserved"]
}

Score 1-10. Be harsh — a score of 8+ means genuinely top 1% quality.
"""

_DOMAIN_EXPERT_INSTRUCTION = """
You are the Domain Expert Critic for SKILL FORGE. Evaluate whether the skill
contains factually accurate, current, and complete domain knowledge.

## Your Evaluation Checklist

- [ ] Every factual claim is accurate for the domain
- [ ] No outdated techniques or deprecated tools mentioned
- [ ] Domain terminology used correctly (matches professional conventions)
- [ ] The skill reflects top 1% expert knowledge (not just common knowledge)
- [ ] Key domain nuances are captured (things experts know that novices miss)
- [ ] No contradictions between different parts of the skill
- [ ] Examples are realistic and domain-appropriate

## Scoring Guide

- 9-10: Reflects deep expert knowledge, no factual errors, captures subtle nuances
- 7-8:  Mostly accurate, minor gaps in domain depth
- 5-6:  Some wrong claims or missing important domain knowledge
- 1-4:  Significant factual errors or fundamentally misunderstands the domain
""" + _CRITIC_OUTPUT_FORMAT

_INSTRUCTION_QUALITY_INSTRUCTION = """
You are the Instruction Quality Critic for SKILL FORGE. Evaluate whether someone
can execute this skill without any ambiguity or guessing.

## Your Evaluation Checklist

- [ ] Every step has a clear, unambiguous action verb
- [ ] Each step can be executed independently (no hidden dependencies)
- [ ] Examples match the instructions exactly (no contradictions)
- [ ] Step ordering is logical — no step requires information from a later step
- [ ] Quality checklist items are binary pass/fail (not subjective)
- [ ] Role statement is specific enough to anchor behavior
- [ ] No vague directives ("be thorough", "consider", "ensure quality")
- [ ] Failure guards are specific enough to catch real failures

## Scoring Guide

- 9-10: Zero ambiguity, perfect clarity, a first-time user succeeds immediately
- 7-8:  1-2 minor ambiguities, easily resolved
- 5-6:  Multiple confusing or contradictory steps
- 1-4:  Instructions cannot be followed without guessing
""" + _CRITIC_OUTPUT_FORMAT

_EDGE_CASE_INSTRUCTION = """
You are the Edge Case Critic for SKILL FORGE. Generate adversarial test scenarios
and evaluate how well the skill handles them.

## Your Task

1. Generate 10 adversarial test scenarios for this skill:
   - 3 common-but-tricky cases (normal input, subtle difficulty)
   - 3 edge cases (boundary conditions, missing information, extremes)
   - 2 adversarial cases (conflicting premises, misleading context)
   - 2 failure-mode cases (exactly the failure modes the skill should guard against)

2. For each scenario, predict whether the current skill would handle it correctly.

3. Score the skill based on predicted robustness.

## Scoring Guide

- 9-10: Handles all 10 scenarios correctly, including adversarial ones
- 7-8:  Fails on 1-2 rare edge cases only
- 5-6:  Fails on 20-30% of scenarios
- 1-4:  Brittle, fails on common variations

Include the 10 test scenarios in your corrections field (as JSON strings).
""" + _CRITIC_OUTPUT_FORMAT


def make_domain_expert_critic(skill_content: str, domain: str) -> Agent:
    return Agent(
        model=MODEL,
        name="domain_expert_critic",
        description=f"Evaluates factual accuracy and domain depth of a skill for: {domain}",
        instruction=_DOMAIN_EXPERT_INSTRUCTION + f"\n\n## Skill to Evaluate\n\n{skill_content}",
        tools=[],
    )


def make_instruction_quality_critic(skill_content: str) -> Agent:
    return Agent(
        model=MODEL,
        name="instruction_quality_critic",
        description="Evaluates clarity, actionability, and executability of skill instructions",
        instruction=_INSTRUCTION_QUALITY_INSTRUCTION + f"\n\n## Skill to Evaluate\n\n{skill_content}",
        tools=[],
    )


def make_edge_case_critic(skill_content: str, domain: str) -> Agent:
    return Agent(
        model=MODEL,
        name="edge_case_critic",
        description=f"Generates adversarial test scenarios and evaluates skill robustness for: {domain}",
        instruction=_EDGE_CASE_INSTRUCTION + f"\n\n## Skill to Evaluate\n\n{skill_content}",
        tools=[],
    )


def compute_panel_composite(scores: list[CriticScore]) -> float:
    """Simple average of the three critic scores for panel composite."""
    return sum(s.score for s in scores) / len(scores)


def should_trigger_debate(scores: list[CriticScore]) -> bool:
    """True if any two critics diverge by more than 2 points."""
    values = [s.score for s in scores]
    return (max(values) - min(values)) > 2.0
```

- [ ] **Step 4: Run — confirm pass**

```bash
cd aass_agents && python -m pytest tests/skill_forge/test_critic_panel.py -v
```

- [ ] **Step 5: Commit**

```bash
git add aass_agents/agents/skill_forge/critic_panel_agent.py \
        aass_agents/tests/skill_forge/test_critic_panel.py
git commit -m "feat: add critic_panel_agent — A-HMAD heterogeneous debate with 3 critic agents"
```

---

## Phase 4: Validation Pipeline

### Task 8: Red Team Agent

**Files:**
- Create: `aass_agents/agents/skill_forge/red_team_agent.py`
- Create: `aass_agents/tests/skill_forge/test_red_team.py`

- [ ] **Step 1: Write failing tests**

```python
# aass_agents/tests/skill_forge/test_red_team.py
import pytest
from agents.skill_forge.red_team_agent import (
    make_red_team_agent,
    build_test_case_distribution,
    compute_battle_test_report,
)
from agents.skill_forge.models import BattleTestReport


def test_test_case_distribution_sums_to_100():
    dist = build_test_case_distribution(total=100)
    assert sum(dist.values()) == 100
    assert dist["common"] == 40
    assert dist["edge"] == 30
    assert dist["adversarial"] == 20
    assert dist["regression"] == 10


def test_compute_battle_test_report():
    results = [
        {"category": "common", "passed": True},
        {"category": "common", "passed": True},
        {"category": "edge", "passed": False},
        {"category": "adversarial", "passed": True},
    ]
    report = compute_battle_test_report(results, worst_cases=["case_2"])
    assert report.total_cases == 4
    assert report.passed == 3
    assert report.pass_rate() == pytest.approx(0.75)
    assert report.failure_breakdown["edge"] == 1


def test_battle_test_report_confidence_interval():
    # 89/100 pass rate
    results = [{"category": "common", "passed": i < 89} for i in range(100)]
    worst = []
    report = compute_battle_test_report(results, worst_cases=worst)
    lower, upper = report.confidence_interval_95()
    assert 0.80 < lower < 0.89
    assert 0.89 < upper < 1.0


def test_make_red_team_agent_returns_agent():
    from google.adk.agents import Agent
    skill_content = "# Test\n\n## Instructions\n\n### Step 1\n- [ ] Do it"
    agent = make_red_team_agent(skill_content, domain="test domain", edge_cases=[])
    assert isinstance(agent, Agent)
    assert agent.name == "red_team_agent"
```

- [ ] **Step 2: Run — confirm fail**

```bash
cd aass_agents && python -m pytest tests/skill_forge/test_red_team.py -v
```

- [ ] **Step 3: Implement**

```python
# aass_agents/agents/skill_forge/red_team_agent.py
"""
Red Team Agent — generates and runs 100 adversarial test cases against a skill.

Distribution: 40 common / 30 edge / 20 adversarial / 10 regression
Output: BattleTestReport with pass_rate, CI, worst_cases, failure_breakdown.
"""
import os
from google.adk.agents import Agent
from agents.skill_forge.models import BattleTestReport

MODEL = os.getenv("MODEL_ID", "gemini-2.0-flash")

INSTRUCTION = """
You are the Red Team Agent for SKILL FORGE. Your job: generate 100 test cases
for a skill and predict which ones would pass or fail.

## Test Case Distribution

Generate exactly:
- 40 COMMON cases: standard, expected inputs the skill will see daily
- 30 EDGE cases: boundary conditions, missing info, extremes, unusual-but-valid
- 20 ADVERSARIAL cases: conflicting premises, misleading context, prompt injection attempts, trick inputs
- 10 REGRESSION cases: inputs that match known failure modes from the skill's failure guards

## For Each Test Case

Generate:
1. A specific input scenario (concrete, not generic)
2. What the skill SHOULD produce (expected behavior)
3. What failure looks like (failure_signal)
4. Your verdict: PASS or FAIL based on the current skill instructions

## Output Format

Return ONLY valid JSON:
{
  "test_cases": [
    {
      "case_id": "tc_001",
      "category": "common | edge | adversarial | regression",
      "input": "specific input scenario",
      "expected_behavior": "what correct output looks like",
      "failure_signal": "what wrong output looks like",
      "verdict": "PASS | FAIL",
      "failure_reason": "null or explanation if FAIL"
    },
    ...
  ],
  "summary": {
    "total": 100,
    "passed": N,
    "failed": N,
    "failure_breakdown": {"common": N, "edge": N, "adversarial": N, "regression": N}
  }
}

Be HARSH. If the skill doesn't explicitly handle a scenario, predict FAIL.
A PASS is only warranted if the skill instructions clearly cover this case.
"""


def build_test_case_distribution(total: int = 100) -> dict[str, int]:
    return {
        "common": int(total * 0.40),
        "edge": int(total * 0.30),
        "adversarial": int(total * 0.20),
        "regression": int(total * 0.10),
    }


def compute_battle_test_report(
    results: list[dict], worst_cases: list[str]
) -> BattleTestReport:
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    breakdown: dict[str, int] = {}
    for r in results:
        if not r["passed"]:
            cat = r.get("category", "unknown")
            breakdown[cat] = breakdown.get(cat, 0) + 1
    return BattleTestReport(
        total_cases=total,
        passed=passed,
        failure_breakdown=breakdown,
        worst_cases=worst_cases,
    )


def make_red_team_agent(
    skill_content: str,
    domain: str,
    edge_cases: list[str],
) -> Agent:
    edge_cases_text = "\n".join(f"- {e}" for e in edge_cases) if edge_cases else "None provided"
    return Agent(
        model=MODEL,
        name="red_team_agent",
        description=(
            f"Generates 100 adversarial test cases for a {domain} skill and predicts "
            "pass/fail for each. Returns BattleTestReport with failure breakdown."
        ),
        instruction=(
            INSTRUCTION
            + f"\n\n## Skill to Red-Team\n\n{skill_content}"
            + f"\n\n## Known Edge Cases from Critics\n{edge_cases_text}"
            + f"\n\n## Domain Context\n{domain}"
        ),
        tools=[],
    )
```

- [ ] **Step 4: Run — confirm pass**

```bash
cd aass_agents && python -m pytest tests/skill_forge/test_red_team.py -v
```

- [ ] **Step 5: Commit**

```bash
git add aass_agents/agents/skill_forge/red_team_agent.py \
        aass_agents/tests/skill_forge/test_red_team.py
git commit -m "feat: add red_team_agent — 100-case adversarial battle-testing with CI gating"
```

---

### Task 9: Iteration Agent

**Files:**
- Create: `aass_agents/agents/skill_forge/iteration_agent.py`
- Create: `aass_agents/tests/skill_forge/test_iteration_agent.py`

- [ ] **Step 1: Write failing tests**

```python
# aass_agents/tests/skill_forge/test_iteration_agent.py
import pytest
from agents.skill_forge.iteration_agent import (
    make_iteration_agent,
    should_continue_loop,
    should_rollback,
)
from agents.skill_forge.models import CompositeScore


def test_should_continue_when_below_threshold():
    score = CompositeScore(correctness=7.0, robustness=7.0, clarity=7.0, domain_accuracy=7.0)
    assert should_continue_loop(score, iteration=3, max_iterations=10) is True


def test_should_stop_when_threshold_met():
    score = CompositeScore(correctness=9.0, robustness=9.0, clarity=9.0, domain_accuracy=9.0)
    assert should_continue_loop(score, iteration=3, max_iterations=10) is False


def test_should_stop_at_max_iterations():
    score = CompositeScore(correctness=7.0, robustness=7.0, clarity=7.0, domain_accuracy=7.0)
    assert should_continue_loop(score, iteration=10, max_iterations=10) is False


def test_should_rollback_on_regression():
    prev = CompositeScore(correctness=8.0, robustness=8.0, clarity=8.0, domain_accuracy=8.0)
    curr = CompositeScore(correctness=7.0, robustness=7.0, clarity=7.5, domain_accuracy=7.5)
    # prev composite = 8.0, curr composite ≈ 7.25, delta = 0.75 > 0.5
    assert should_rollback(current=curr, previous=prev, regression_threshold=0.5) is True


def test_should_not_rollback_on_improvement():
    prev = CompositeScore(correctness=7.5, robustness=7.5, clarity=7.5, domain_accuracy=7.5)
    curr = CompositeScore(correctness=8.0, robustness=8.0, clarity=8.0, domain_accuracy=8.0)
    assert should_rollback(current=curr, previous=prev, regression_threshold=0.5) is False


def test_make_iteration_agent_returns_agent():
    from google.adk.agents import Agent
    agent = make_iteration_agent(
        skill_content="# skill",
        worst_cases=["case1"],
        composite_score=7.5,
        iteration=1,
    )
    assert isinstance(agent, Agent)
    assert agent.name == "iteration_agent"
```

- [ ] **Step 2: Run — confirm fail**

```bash
cd aass_agents && python -m pytest tests/skill_forge/test_iteration_agent.py -v
```

- [ ] **Step 3: Implement**

```python
# aass_agents/agents/skill_forge/iteration_agent.py
"""
Iteration Agent — GEPA reflective loop for skill improvement.

Pattern: reflect on WHY worst cases failed → targeted patch → re-test.
Continues until composite ≥ 8.5 or 10 iterations reached.
Rolls back if a patch causes composite to drop > 0.5 points.
"""
import os
from google.adk.agents import Agent
from agents.skill_forge.models import CompositeScore

MODEL = os.getenv("MODEL_ID", "gemini-2.0-flash")

INSTRUCTION = """
You are the Iteration Agent for SKILL FORGE. You apply GEPA (reflective prompt
evolution) to improve a skill based on its worst-performing test cases.

## Your Process

### Step 1: Reflect on Failures (GEPA)

For each failing test case, ask:
- WHY did this specific case fail? (root cause, not surface symptom)
- WHAT specific instruction change would fix this without breaking passing cases?
- Is this failure an isolated edge case or a systemic gap?

Prioritize systemic gaps over isolated edge cases.

### Step 2: Generate Targeted Patch

Write a MINIMAL patch to the skill instructions:
- Change only what's needed to fix the identified root cause
- Never rewrite sections that are working well
- Add a specific guard or clarification where the failure occurred
- Preserve all passing examples and working steps

### Step 3: Output Format

Return ONLY valid JSON:
{
  "reflection": [
    {
      "case": "description of failing case",
      "root_cause": "WHY it failed (specific instruction gap)",
      "fix_type": "add_guard | clarify_step | add_example | restructure_step"
    }
  ],
  "patch_description": "1-2 sentences summarizing what changed and why",
  "patched_skill_content": "THE COMPLETE UPDATED SKILL.MD CONTENT HERE"
}

The patched_skill_content must be the full, complete SKILL.md — not a diff.

## Rules

- Never remove examples that are working
- Never change the overall structure if it's passing critique
- Targeted fixes only — minimum viable change
- If the root cause is ambiguous, add an explicit clarification to the relevant step
"""

STAGING_THRESHOLD = 8.5
MAX_ITERATIONS = 10
REGRESSION_THRESHOLD = 0.5


def should_continue_loop(
    score: CompositeScore, iteration: int, max_iterations: int = MAX_ITERATIONS
) -> bool:
    if iteration >= max_iterations:
        return False
    return not score.passes_staging_gate()


def should_rollback(
    current: CompositeScore,
    previous: CompositeScore,
    regression_threshold: float = REGRESSION_THRESHOLD,
) -> bool:
    return (previous.composite() - current.composite()) > regression_threshold


def make_iteration_agent(
    skill_content: str,
    worst_cases: list[str],
    composite_score: float,
    iteration: int,
) -> Agent:
    worst_cases_text = "\n".join(f"- {c}" for c in worst_cases[:20])
    return Agent(
        model=MODEL,
        name="iteration_agent",
        description=(
            f"GEPA iteration {iteration}: reflects on failing test cases and generates "
            f"targeted patch. Current composite: {composite_score:.2f}/10."
        ),
        instruction=(
            INSTRUCTION
            + f"\n\n## Current Skill (composite score: {composite_score:.2f}/10)\n\n{skill_content}"
            + f"\n\n## Worst Failing Test Cases (fix these)\n{worst_cases_text}"
            + f"\n\n## Iteration Number\n{iteration} of {MAX_ITERATIONS} max"
        ),
        tools=[],
    )
```

- [ ] **Step 4: Run — confirm pass**

```bash
cd aass_agents && python -m pytest tests/skill_forge/test_iteration_agent.py -v
```

- [ ] **Step 5: Commit**

```bash
git add aass_agents/agents/skill_forge/iteration_agent.py \
        aass_agents/tests/skill_forge/test_iteration_agent.py
git commit -m "feat: add iteration_agent — GEPA reflective loop with rollback on regression"
```

---

### Task 10: Promoter Agent + Staging Registry

**Files:**
- Create: `aass_agents/agents/skill_forge/promoter_agent.py`
- Create: `aass_agents/tests/skill_forge/test_promoter.py`

- [ ] **Step 1: Write failing tests**

```python
# aass_agents/tests/skill_forge/test_promoter.py
import json
import pytest
from pathlib import Path
from unittest.mock import patch
from agents.skill_forge.promoter_agent import (
    make_promoter_agent,
    write_to_staging_registry,
    generate_audit_md,
    generate_metadata_json,
    check_production_promotion,
)
from agents.skill_forge.models import TaskSpec, BattleTestReport, CompositeScore


@pytest.fixture
def sample_spec():
    return TaskSpec(
        task_name="VC Pitch Deck Writing",
        domain="venture capital fundraising",
        skill_type="writing",
        success_definition="investor requests follow-up",
        scope_boundaries="seed/series A",
        existing_skill_path=None,
        department="generated",
        priority="high",
    )


@pytest.fixture
def sample_report():
    return BattleTestReport(
        total_cases=100,
        passed=89,
        failure_breakdown={"common": 1, "edge": 5, "adversarial": 3, "regression": 2},
        worst_cases=["case1", "case2"],
    )


@pytest.fixture
def sample_score():
    return CompositeScore(
        correctness=9.0,
        robustness=8.4,
        clarity=8.6,
        domain_accuracy=8.9,
    )


def test_generate_audit_md_contains_score(sample_spec, sample_report, sample_score):
    audit = generate_audit_md(sample_spec, sample_report, sample_score, iterations=3)
    assert "8.5" in audit or str(round(sample_score.composite(), 1)) in audit
    assert "89%" in audit or "89" in audit
    assert "VC Pitch Deck Writing" in audit


def test_generate_metadata_json(sample_spec, sample_report, sample_score):
    metadata = generate_metadata_json(sample_spec, sample_report, sample_score, version=5)
    assert metadata["skill_name"] == "VC Pitch Deck Writing"
    assert metadata["composite_score"] == pytest.approx(sample_score.composite(), abs=0.01)
    assert metadata["version"] == 5
    assert metadata["production_runs"] == 0


def test_write_to_staging_registry(tmp_path, sample_spec, sample_report, sample_score):
    skill_content = "# Test Skill\n\n## Instructions\n- [ ] Do thing"
    write_to_staging_registry(
        base_path=tmp_path,
        spec=sample_spec,
        skill_content=skill_content,
        report=sample_report,
        score=sample_score,
        test_cases=[],
        iterations=3,
        needs_review=False,
    )
    skill_dir = tmp_path / "venture-capital-fundraising" / "vc-pitch-deck-writing"
    assert (skill_dir / "SKILL.md").exists()
    assert (skill_dir / "metadata.json").exists()
    assert (skill_dir / "AUDIT.md").exists()
    assert (skill_dir / "test_suite.json").exists()


def test_check_production_promotion_ready():
    assert check_production_promotion(production_runs=5, avg_score=7.5) is True


def test_check_production_promotion_not_ready():
    assert check_production_promotion(production_runs=3, avg_score=7.5) is False
    assert check_production_promotion(production_runs=5, avg_score=6.5) is False
```

- [ ] **Step 2: Run — confirm fail**

```bash
cd aass_agents && python -m pytest tests/skill_forge/test_promoter.py -v
```

- [ ] **Step 3: Implement**

```python
# aass_agents/agents/skill_forge/promoter_agent.py
"""
Promoter Agent — runs confidence gate and writes validated skills to staging registry.

Staging structure:
  generated_skills/{domain}/{skill-name}/
    SKILL.md          final skill
    metadata.json     scores, versions, timestamps
    test_suite.json   100 test cases for regression
    AUDIT.md          human-readable audit trail

Production promotion: auto-triggered when production_runs >= 5 AND avg >= 7.0.
"""
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

from google.adk.agents import Agent

from agents.skill_forge.models import BattleTestReport, CompositeScore, TaskSpec

MODEL = os.getenv("MODEL_ID", "gemini-2.0-flash")
PRODUCTION_RUNS_NEEDED = 5
PRODUCTION_AVG_THRESHOLD = 7.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def generate_audit_md(
    spec: TaskSpec,
    report: BattleTestReport,
    score: CompositeScore,
    iterations: int,
) -> str:
    lower, upper = report.confidence_interval_95()
    composite = score.composite()
    pass_pct = int(report.pass_rate() * 100)
    return f"""# Skill Audit: {spec.task_name}
Generated: {_now_iso()}  |  Iterations: {iterations}

## Composite Score: {composite:.1f} / 10

| Dimension           | Score | Weight | Weighted |
|---------------------|-------|--------|---------|
| Correctness         | {score.correctness:.1f}   | 0.35   | {0.35 * score.correctness:.2f}    |
| Robustness          | {score.robustness:.1f}   | 0.25   | {0.25 * score.robustness:.2f}    |
| Instruction Clarity | {score.clarity:.1f}   | 0.20   | {0.20 * score.clarity:.2f}    |
| Domain Accuracy     | {score.domain_accuracy:.1f}   | 0.20   | {0.20 * score.domain_accuracy:.2f}    |

## Battle-Test Results

- Total cases: {report.total_cases}
- Pass rate: {pass_pct}% (CI: {int(lower*100)}-{int(upper*100)}%, 95% confidence)

## Failure Breakdown

| Category    | Cases | Failed |
|-------------|-------|--------|
| Common      | 40    | {report.failure_breakdown.get('common', 0)}      |
| Edge        | 30    | {report.failure_breakdown.get('edge', 0)}      |
| Adversarial | 20    | {report.failure_breakdown.get('adversarial', 0)}      |
| Regression  | 10    | {report.failure_breakdown.get('regression', 0)}      |

## Domain

{spec.domain}

## Success Definition

{spec.success_definition}
"""


def generate_metadata_json(
    spec: TaskSpec,
    report: BattleTestReport,
    score: CompositeScore,
    version: int,
) -> dict:
    lower, upper = report.confidence_interval_95()
    return {
        "skill_name": spec.task_name,
        "domain": spec.domain,
        "skill_type": spec.skill_type,
        "department": spec.department,
        "composite_score": round(score.composite(), 3),
        "correctness": score.correctness,
        "robustness": score.robustness,
        "clarity": score.clarity,
        "domain_accuracy": score.domain_accuracy,
        "pass_rate": round(report.pass_rate(), 3),
        "ci_lower": round(lower, 3),
        "ci_upper": round(upper, 3),
        "version": version,
        "production_runs": 0,
        "promoted_at": None,
        "created_at": _now_iso(),
    }


def write_to_staging_registry(
    base_path: Path,
    spec: TaskSpec,
    skill_content: str,
    report: BattleTestReport,
    score: CompositeScore,
    test_cases: list[dict],
    iterations: int,
    needs_review: bool,
) -> Path:
    domain_slug = spec.domain.lower().replace(" ", "-").replace("/", "-")[:40]
    skill_dir = base_path / domain_slug / spec.slug()
    skill_dir.mkdir(parents=True, exist_ok=True)

    (skill_dir / "SKILL.md").write_text(skill_content, encoding="utf-8")
    (skill_dir / "AUDIT.md").write_text(
        generate_audit_md(spec, report, score, iterations), encoding="utf-8"
    )
    metadata = generate_metadata_json(spec, report, score, version=iterations)
    metadata["needs_review"] = needs_review
    (skill_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    (skill_dir / "test_suite.json").write_text(
        json.dumps(test_cases, indent=2), encoding="utf-8"
    )
    return skill_dir


def check_production_promotion(production_runs: int, avg_score: float) -> bool:
    return production_runs >= PRODUCTION_RUNS_NEEDED and avg_score >= PRODUCTION_AVG_THRESHOLD


def make_promoter_agent(spec: TaskSpec, score: CompositeScore, report: BattleTestReport) -> Agent:
    lower, _ = report.confidence_interval_95()
    return Agent(
        model=MODEL,
        name="promoter_agent",
        description=(
            f"Runs confidence gate and writes '{spec.task_name}' to staging registry. "
            f"Composite: {score.composite():.2f}/10, CI lower: {lower:.2f}, "
            f"Pass rate: {report.pass_rate():.0%}"
        ),
        instruction=(
            "You are the Promoter Agent. Confirm the skill passes all gates, then "
            "report the staging location and next steps for production promotion."
        ),
        tools=[],
    )
```

- [ ] **Step 4: Run — confirm pass**

```bash
cd aass_agents && python -m pytest tests/skill_forge/test_promoter.py -v
```

- [ ] **Step 5: Create `generated_skills/` registry root**

```bash
mkdir -p generated_skills
echo '{"skills": [], "last_updated": null}' > generated_skills/_registry.json
```

- [ ] **Step 6: Commit**

```bash
git add aass_agents/agents/skill_forge/promoter_agent.py \
        aass_agents/tests/skill_forge/test_promoter.py \
        generated_skills/_registry.json
git commit -m "feat: add promoter_agent — confidence gate, staging registry, AUDIT.md generation"
```

---

### Task 11: Orchestrator Agent + /forge Skill

**Files:**
- Create: `aass_agents/agents/skill_forge/orchestrator_agent.py`
- Create: `aass_agents/skills/skill-forge/SKILL.md`
- Create: `aass_agents/tests/skill_forge/test_orchestrator_e2e.py`

- [ ] **Step 1: Write failing e2e test**

```python
# aass_agents/tests/skill_forge/test_orchestrator_e2e.py
import pytest
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock
from agents.skill_forge.orchestrator_agent import make_forge_orchestrator
from google.adk.agents import Agent


def test_make_forge_orchestrator_returns_agent():
    agent = make_forge_orchestrator()
    assert isinstance(agent, Agent)
    assert agent.name == "skill_forge_orchestrator"


def test_forge_orchestrator_has_description():
    agent = make_forge_orchestrator()
    assert "skill" in agent.description.lower()
    assert "forge" in agent.description.lower() or "generate" in agent.description.lower()


def test_skill_md_exists():
    skill_path = Path("aass_agents/skills/skill-forge/SKILL.md")
    assert skill_path.exists(), "SKILL.md must exist at aass_agents/skills/skill-forge/SKILL.md"


def test_skill_md_has_required_frontmatter():
    skill_path = Path("aass_agents/skills/skill-forge/SKILL.md")
    content = skill_path.read_text()
    assert "name: skill-forge" in content
    assert "description:" in content


def test_skill_md_has_trigger_phrases():
    skill_path = Path("aass_agents/skills/skill-forge/SKILL.md")
    content = skill_path.read_text()
    assert "generate skill for" in content.lower() or "forge" in content.lower()
```

- [ ] **Step 2: Run — confirm fail**

```bash
cd aass_agents && python -m pytest tests/skill_forge/test_orchestrator_e2e.py -v
```

- [ ] **Step 3: Implement orchestrator**

```python
# aass_agents/agents/skill_forge/orchestrator_agent.py
"""
SKILL FORGE Orchestrator — coordinates all 8 pipeline stages.

Triggered by: /forge "task description" or forge_skill(request="...")
Persists all state to skill_forge.db for crash recovery.
Output: staged skill at generated_skills/{domain}/{skill-name}/
"""
import os
from google.adk.agents import Agent

MODEL = os.getenv("MODEL_ID", "gemini-2.0-flash")

INSTRUCTION = """
You are the SKILL FORGE Orchestrator. You autonomously generate battle-tested
Claude Code skills from a single NLP sentence across 8 pipeline stages.

## Pipeline Stages

1. INTENT: Parse NLP → TaskSpec (ask ONE question max if ambiguous)
2. RESEARCH: Spawn 3 parallel researchers (domain, benchmark, technique)
3. SYNTHESIZE: Distill bundles → ExpertBlueprint
4. DRAFT: Generate SKILL.md v0 from blueprint
5. CRITIQUE: 3-critic A-HMAD panel (debate if diverge >2pts); loop max 3x if <7.5
6. BATTLE-TEST: Red team 100 cases (40/30/20/10 distribution)
7. ITERATE: GEPA loop until composite ≥ 8.5 or 10 iterations (rollback on regression)
8. PROMOTE: CI gate → write to generated_skills/ → report to user

## Resume Protocol

On start, check skill_forge.db for in-progress sessions. If found:
- Read current_stage from forge_sessions
- Resume from that stage (don't redo completed stages)
- Log: "Resuming session {id} from stage {stage}"

## Quality Gates

- Critique gate: composite ≥ 7.5 (else back to Drafter, max 3 cycles)
- Staging gate: composite ≥ 8.5 AND CI lower ≥ 0.80
- If best score < 7.0 after all iterations: do NOT stage, surface to user

## Final Summary Format

```
SKILL FORGE SUMMARY
════════════════════════════════════════════
Skill:          {skill_name}
Domain:         {domain}
Staged at:      generated_skills/{path}/

── PIPELINE RESULTS ────────────────────────
Research:       3 bundles
Draft cycles:   {N}
Iterations:     {N} (GEPA loop)

── FINAL SCORES ────────────────────────────
Correctness:    {score}/10
Robustness:     {score}/10
Clarity:        {score}/10
Domain Accuracy:{score}/10
COMPOSITE:      {score}/10

── BATTLE-TEST ─────────────────────────────
Pass rate:      {N}% (CI: {low}-{high}%, 95%)
Cases run:      100 (40/30/20/10)

── STATUS ──────────────────────────────────
Staged:         ✓ generated_skills/{path}/
Production:     Pending ({runs}/5 runs needed)
════════════════════════════════════════════
```
"""


def make_forge_orchestrator() -> Agent:
    return Agent(
        model=MODEL,
        name="skill_forge_orchestrator",
        description=(
            "Orchestrates the full SKILL FORGE pipeline: research → synthesize → "
            "draft → critique → battle-test → iterate → promote. Call with a natural "
            "language skill request. Returns a staged, battle-tested SKILL.md."
        ),
        instruction=INSTRUCTION,
        tools=[],
    )


skill_forge_orchestrator = make_forge_orchestrator()
```

- [ ] **Step 4: Write the /forge SKILL.md**

Create file at `aass_agents/skills/skill-forge/SKILL.md` with the full orchestrator skill content from the design spec (the complete SKILL.md shown in Section 5 of the design doc).

```bash
mkdir -p aass_agents/skills/skill-forge
```

Then write `aass_agents/skills/skill-forge/SKILL.md`:

```markdown
---
name: skill-forge
description: >
  Invoke to autonomously generate, battle-test, and stage a new Claude Code skill
  for any task. Trigger phrases: "generate skill for", "create a skill that",
  "build me a skill to", "forge skill", "/forge". Takes a natural language task
  description and runs a full 8-stage pipeline: research → synthesize → draft →
  critique → red-team → iterate → promote. Output is a battle-tested SKILL.md
  staged in generated_skills/ with a full AUDIT.md and test suite.
---

# SKILL FORGE Orchestrator

You are the SKILL FORGE Orchestrator. Your purpose is to autonomously generate
production-quality, battle-tested Claude Code skills from a single NLP sentence.
You coordinate 12 specialized sub-agents across 8 pipeline stages, persisting all
state to skill_forge.db so any stage can resume after interruption.

## Instructions

### Step 1: Parse Intent

Route to intent_parser_agent with the raw NLP input.
- If TaskSpec is ambiguous on domain or success_definition: ask ONE clarifying question.
- If task matches an existing skill in aass_agents/skills/: confirm upgrade vs. new parallel skill.
- Log session to skill_forge.db (stage: intent).

### Step 2: Research Swarm (parallel)

Launch 3 research agents in parallel:
- domain_researcher: expert knowledge, mental models, best practices
- benchmark_researcher: top 1% outputs, gold standards, human baselines
- technique_researcher: tools, frameworks, prompting patterns for this task type

Wait for all 3 to complete. If 1 fails: retry once, proceed with 2/3 minimum.
Log all bundles to skill_forge.db (stage: research).

### Step 3: Expert Synthesis

Route to expert_synthesizer_agent with all 3 ResearchBundles.
Output: ExpertBlueprint (constitutional principles, gold examples, failure modes).
Log to skill_forge.db (stage: synthesize).

### Step 4: Skill Draft

Route to skill_drafter_agent with TaskSpec + ExpertBlueprint.
Output: SKILL.md v0. Log to skill_versions (version: v0).

### Step 5: Critic Panel (parallel, A-HMAD)

Launch 3 critic agents in parallel:
- domain_expert_critic: factual accuracy, completeness
- instruction_quality_critic: clarity, actionability, ambiguity
- edge_case_critic: generates 10 adversarial scenarios, tests each

Collect scores. If any two critics diverge by >2 points: run one debate round.
Compute composite score (simple average of 3 critic scores for panel).

If composite < 7.5:
  - Return to skill_drafter_agent with critic notes
  - Max 3 draft-critique cycles
  - If still < 7.5 after 3: flag session as stalled, surface to user

Log to skill_forge.db (stage: critique).

### Step 6: Battle-Test

Route to red_team_agent with current SKILL.md + edge_case_critic scenarios.
Output: BattleTestReport (100 cases: 40 common / 30 edge / 20 adversarial / 10 regression).
Log to battle_test_results.

### Step 7: GEPA Iteration Loop

Route to iteration_agent.

Loop:
  - Reflect on worst_cases: "Why did X fail? What specific instruction change fixes this?"
  - Patch SKILL.md (targeted, not full rewrite)
  - Re-run red team on worst_cases only (fast loop, 20 cases)
  - Log new version to skill_versions
  - If composite regresses > 0.5: rollback to previous version
  - Break if composite ≥ 8.5 or iterations ≥ 10

If best score < 8.5 after 10 iterations:
  - Promote best version with needs_review: true flag

If best score < 7.0:
  - Do NOT stage. Surface to user with explanation of what's hard about this task.

### Step 8: Promote to Staging

Run confidence gate:
  - CI lower bound ≥ 0.80
  - Composite ≥ 8.5 (or best achieved with needs_review flag)

Write to generated_skills/{domain}/{skill-name}/:
  - SKILL.md (final version)
  - metadata.json (scores, versions, timestamps)
  - test_suite.json (100 cases for regression)
  - AUDIT.md (full human-readable audit trail)

Update generated_skills/_registry.json.

### Step 9: Report

Output a SKILL FORGE SUMMARY (see format in orchestrator_agent.py).

Offer next steps:
- "Review AUDIT.md for full details"
- "Run the skill now on a test input"
- "Trigger production promotion manually if confidence is high"

## Quality Standards

- Never skip battle-test stage, even for simple tasks
- Never promote directly to aass_agents/skills/ — always stage first
- Every promoted skill must ship with test_suite.json for future regression testing
- Auto-promote to aass_agents/skills/ when production_runs ≥ 5 AND avg score ≥ 7.0
- Demote back to staging if 2 consecutive production runs score < 6.0

## Integration Notes

- Reads evolution.db to check if task domain has existing agent history
- Writes production_runs to staging_registry as reflection_agent logs scores
- skill_forge.db persists all pipeline state — crashed runs resume automatically
```

- [ ] **Step 5: Run all tests**

```bash
cd aass_agents && python -m pytest tests/skill_forge/ -v
```
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add aass_agents/agents/skill_forge/orchestrator_agent.py \
        aass_agents/skills/skill-forge/SKILL.md \
        aass_agents/tests/skill_forge/test_orchestrator_e2e.py
git commit -m "feat: add skill_forge orchestrator + /forge SKILL.md — complete pipeline assembled"
```

---

### Task 12: Full Test Suite Run + Coverage

**Files:**
- No new files — run coverage across all skill_forge tests

- [ ] **Step 1: Run full suite with coverage**

```bash
cd aass_agents && python -m pytest tests/skill_forge/ -v --cov=agents/skill_forge --cov=tools/skill_forge_db --cov-report=term-missing
```

Expected output includes coverage summary. Target: ≥ 80% coverage.

- [ ] **Step 2: Fix any failing tests**

If any tests fail, diagnose and fix before proceeding. Do not skip tests.

- [ ] **Step 3: Run full aass_agents test suite to confirm no regressions**

```bash
cd aass_agents && python -m pytest --ignore=tests/skill_forge/ -v
```

Expected: All existing tests still PASS (no regressions from new code).

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "test: full skill_forge test suite — all phases covered, no regressions"
```

---

## Spec Coverage Check

| Spec Requirement | Task |
|---|---|
| skill_forge.db with 5 tables | Task 1 |
| Immutable data models (TaskSpec, CompositeScore, BattleTestReport) | Task 2 |
| Intent Parser (NLP → TaskSpec, max 1 question) | Task 3 |
| 3 parallel researchers (domain, benchmark, technique) | Task 4 |
| Constitutional AI synthesis → ExpertBlueprint | Task 5 |
| DSPy-style SKILL.md drafter with failure guards | Task 6 |
| A-HMAD 3-critic panel with debate trigger | Task 7 |
| Red team 100 cases (40/30/20/10 distribution) | Task 8 |
| GEPA iteration loop with rollback | Task 9 |
| Confidence gate (CI lower ≥ 0.80), staging registry, AUDIT.md | Task 10 |
| Orchestrator + /forge SKILL.md trigger | Task 11 |
| 80%+ test coverage | Task 12 |
| generated_skills/ staging structure | Task 10 |
| Resume from crashed stage | Task 11 (orchestrator instruction) |
| Auto-promote after 5 production runs | Task 10 (check_production_promotion) |
