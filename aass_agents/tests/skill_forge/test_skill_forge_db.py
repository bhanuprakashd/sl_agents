"""
Unit tests for tools/skill_forge_db.py

Uses an isolated SQLite DB (monkeypatched path) so tests never touch the real
skill_forge.db file.
"""
import sqlite3
import pytest

import tools.skill_forge_db as sfdb


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Point skill_forge_db at a fresh temp file for each test."""
    db_path = tmp_path / "test_skill_forge.db"
    monkeypatch.setattr(sfdb, "SKILL_FORGE_DB_PATH", db_path)
    sfdb.init_db()
    yield


# ── init ──────────────────────────────────────────────────────────────────────

def test_init_db_creates_tables(tmp_path, monkeypatch):
    db_path = tmp_path / "fresh.db"
    monkeypatch.setattr(sfdb, "SKILL_FORGE_DB_PATH", db_path)
    sfdb.init_db()
    assert db_path.exists()
    conn = sqlite3.connect(str(db_path))
    tables = {
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    conn.close()
    for table in (
        "forge_sessions",
        "research_bundles",
        "skill_versions",
        "battle_test_results",
        "staging_registry",
    ):
        assert table in tables, f"Table {table!r} not found in DB"


# ── forge_sessions ─────────────────────────────────────────────────────────────

def test_create_session_returns_id():
    task_spec = {"task_name": "test task", "domain": "testing"}
    session_id = sfdb.create_session_sync(task_spec, "intent")
    assert isinstance(session_id, int)
    assert session_id > 0


def test_get_session_returns_dict():
    task_spec = {"task_name": "my skill", "domain": "sales"}
    session_id = sfdb.create_session_sync(task_spec, "intent")
    session = sfdb.get_session_sync(session_id)
    assert session is not None
    assert session["id"] == session_id
    assert session["current_stage"] == "intent"
    assert session["status"] == "active"
    assert session["task_spec"] == task_spec


def test_get_session_returns_none_for_missing():
    result = sfdb.get_session_sync(999999)
    assert result is None


def test_update_session_stage():
    session_id = sfdb.create_session_sync({"task_name": "x"}, "intent")
    sfdb.update_session_stage_sync(session_id, "research")
    session = sfdb.get_session_sync(session_id)
    assert session["current_stage"] == "research"


def test_update_session_status():
    session_id = sfdb.create_session_sync({"task_name": "x"}, "intent")
    sfdb.update_session_status_sync(session_id, "completed")
    session = sfdb.get_session_sync(session_id)
    assert session["status"] == "completed"


# ── research_bundles ──────────────────────────────────────────────────────────

def test_save_and_get_research_bundles():
    session_id = sfdb.create_session_sync({}, "intent")
    findings = {"expert_models": ["model1", "model2"]}
    citations = ["source1", "source2"]
    sfdb.save_research_bundle_sync(session_id, "domain", findings, citations)
    bundles = sfdb.get_research_bundles_sync(session_id)
    assert len(bundles) == 1
    assert bundles[0]["researcher_type"] == "domain"
    assert bundles[0]["findings"] == findings
    assert bundles[0]["citations"] == citations


def test_get_research_bundles_multiple_types():
    session_id = sfdb.create_session_sync({}, "intent")
    sfdb.save_research_bundle_sync(session_id, "domain", {"k": "v1"}, ["c1"])
    sfdb.save_research_bundle_sync(session_id, "benchmark", {"k": "v2"}, ["c2"])
    sfdb.save_research_bundle_sync(session_id, "technique", {"k": "v3"}, ["c3"])
    bundles = sfdb.get_research_bundles_sync(session_id)
    assert len(bundles) == 3
    types = {b["researcher_type"] for b in bundles}
    assert types == {"domain", "benchmark", "technique"}


def test_get_research_bundles_empty_for_new_session():
    session_id = sfdb.create_session_sync({}, "intent")
    assert sfdb.get_research_bundles_sync(session_id) == []


# ── skill_versions ────────────────────────────────────────────────────────────

def test_save_skill_version_returns_id():
    session_id = sfdb.create_session_sync({}, "intent")
    version_id = sfdb.save_skill_version_sync(session_id, 1, "# SKILL.md content", 6.5)
    assert isinstance(version_id, int)
    assert version_id > 0


def test_get_best_skill_version_returns_highest_score():
    session_id = sfdb.create_session_sync({}, "intent")
    sfdb.save_skill_version_sync(session_id, 1, "v1 content", 6.5)
    sfdb.save_skill_version_sync(session_id, 2, "v2 content", 7.8)
    sfdb.save_skill_version_sync(session_id, 3, "v3 content", 7.2)
    best = sfdb.get_best_skill_version_sync(session_id)
    assert best is not None
    assert best["version"] == 2
    assert best["composite_score"] == pytest.approx(7.8)
    assert best["skill_content"] == "v2 content"


def test_get_best_skill_version_returns_none_for_new_session():
    session_id = sfdb.create_session_sync({}, "intent")
    assert sfdb.get_best_skill_version_sync(session_id) is None


def test_get_skill_versions_ordered_by_version():
    session_id = sfdb.create_session_sync({}, "intent")
    sfdb.save_skill_version_sync(session_id, 3, "v3", 7.0)
    sfdb.save_skill_version_sync(session_id, 1, "v1", 6.0)
    sfdb.save_skill_version_sync(session_id, 2, "v2", 6.5)
    versions = sfdb.get_skill_versions_sync(session_id)
    assert [v["version"] for v in versions] == [1, 2, 3]


# ── battle_test_results ───────────────────────────────────────────────────────

def test_save_and_get_battle_test():
    session_id = sfdb.create_session_sync({}, "intent")
    sfdb.save_skill_version_sync(session_id, 1, "content", 7.0)
    failure_breakdown = {"common": 2, "edge": 5, "adversarial": 8, "regression": 1}
    test_cases = [{"case_id": "tc_001", "category": "common"}]
    sfdb.save_battle_test_sync(session_id, 1, 0.84, failure_breakdown, test_cases)
    result = sfdb.get_battle_test_sync(session_id, 1)
    assert result is not None
    assert result["pass_rate"] == pytest.approx(0.84)
    assert result["failure_breakdown"] == failure_breakdown
    assert result["test_cases"] == test_cases


def test_get_battle_test_returns_none_for_missing():
    session_id = sfdb.create_session_sync({}, "intent")
    assert sfdb.get_battle_test_sync(session_id, 99) is None


def test_battle_test_latest_record_returned():
    """When a version is re-tested, the most recent result is returned."""
    session_id = sfdb.create_session_sync({}, "intent")
    sfdb.save_battle_test_sync(session_id, 1, 0.75, {}, [])
    sfdb.save_battle_test_sync(session_id, 1, 0.82, {"common": 3}, [])
    result = sfdb.get_battle_test_sync(session_id, 1)
    assert result["pass_rate"] == pytest.approx(0.82)


# ── staging_registry ──────────────────────────────────────────────────────────

def test_stage_skill_and_get():
    sfdb.stage_skill_sync(
        "sales-pitch-writing", "VC Pitch Writing", "sales", "generated",
        "generated_skills/sales/vc-pitch-writing", 8.7, False
    )
    result = sfdb.get_staged_skill_sync("sales-pitch-writing")
    assert result is not None
    assert result["name"] == "VC Pitch Writing"
    assert result["domain"] == "sales"
    assert result["composite_score"] == pytest.approx(8.7)
    assert result["needs_review"] == 0
    assert result["production_runs"] == 0


def test_stage_skill_needs_review_flag():
    sfdb.stage_skill_sync(
        "review-skill", "Needs Review Skill", "test", "generated",
        "path/to/skill", 7.9, True
    )
    result = sfdb.get_staged_skill_sync("review-skill")
    assert result["needs_review"] == 1


def test_get_staged_skill_returns_none_for_missing():
    assert sfdb.get_staged_skill_sync("nonexistent-skill") is None


def test_list_staged_skills():
    sfdb.stage_skill_sync("skill-a", "A", "domain1", "dept", "path/a", 8.5, False)
    sfdb.stage_skill_sync("skill-b", "B", "domain2", "dept", "path/b", 9.0, False)
    skills = sfdb.list_staged_skills_sync()
    assert len(skills) == 2
    ids = {s["skill_id"] for s in skills}
    assert "skill-a" in ids
    assert "skill-b" in ids


def test_increment_production_runs():
    sfdb.stage_skill_sync("prod-skill", "Prod", "domain", "dept", "path", 9.0, False)
    count1 = sfdb.increment_production_runs_sync("prod-skill")
    count2 = sfdb.increment_production_runs_sync("prod-skill")
    count3 = sfdb.increment_production_runs_sync("prod-skill")
    assert count1 == 1
    assert count2 == 2
    assert count3 == 3


def test_increment_production_runs_nonexistent_returns_zero():
    count = sfdb.increment_production_runs_sync("ghost-skill")
    assert count == 0


def test_stage_skill_upsert_preserves_production_runs():
    """Re-staging a skill should not reset production_runs."""
    sfdb.stage_skill_sync("upsert-skill", "Original", "d", "dept", "path", 8.5, False)
    sfdb.increment_production_runs_sync("upsert-skill")
    sfdb.increment_production_runs_sync("upsert-skill")
    # Re-stage with updated score
    sfdb.stage_skill_sync("upsert-skill", "Updated", "d", "dept", "path", 9.1, False)
    result = sfdb.get_staged_skill_sync("upsert-skill")
    assert result["name"] == "Updated"
    assert result["composite_score"] == pytest.approx(9.1)
    assert result["production_runs"] == 2


# ── full pipeline smoke test ──────────────────────────────────────────────────

def test_full_pipeline_session_lifecycle():
    """Smoke test: full DB lifecycle from session creation to staging."""
    # 1. Create session
    task_spec = {"task_name": "write VC pitches", "domain": "fundraising"}
    session_id = sfdb.create_session_sync(task_spec, "intent")

    # 2. Save research bundles
    sfdb.save_research_bundle_sync(session_id, "domain", {"key": "domain findings"}, ["src1"])
    sfdb.save_research_bundle_sync(session_id, "benchmark", {"key": "benchmarks"}, ["src2"])
    sfdb.save_research_bundle_sync(session_id, "technique", {"key": "techniques"}, ["src3"])
    assert len(sfdb.get_research_bundles_sync(session_id)) == 3

    # 3. Advance stage
    sfdb.update_session_stage_sync(session_id, "research")
    assert sfdb.get_session_sync(session_id)["current_stage"] == "research"

    # 4. Save skill version
    v_id = sfdb.save_skill_version_sync(session_id, 1, "# SKILL.md v1", 6.5)
    assert v_id > 0

    # 5. Save battle test
    sfdb.save_battle_test_sync(session_id, 1, 0.88, {"common": 2, "edge": 3}, [])
    test_result = sfdb.get_battle_test_sync(session_id, 1)
    assert test_result["pass_rate"] == pytest.approx(0.88)

    # 6. Save improved version
    sfdb.save_skill_version_sync(session_id, 2, "# SKILL.md v2 improved", 8.7)
    best = sfdb.get_best_skill_version_sync(session_id)
    assert best["version"] == 2

    # 7. Stage the skill
    sfdb.stage_skill_sync(
        "fundraising-vc-pitch-writing", "VC Pitch Writing", "fundraising",
        "generated", "generated_skills/fundraising/vc-pitch-writing", 8.7, False
    )

    # 8. Complete session
    sfdb.update_session_status_sync(session_id, "completed")
    final = sfdb.get_session_sync(session_id)
    assert final["status"] == "completed"
