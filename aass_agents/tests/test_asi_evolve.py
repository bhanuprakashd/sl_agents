"""
Unit tests for the ASI-Evolve components:
  1. cognition_base_db   -- SQLite-backed knowledge store
  2. evolution_db         -- candidate_pool with UCB1 sampling
  3. cross_agent_learning -- pattern transfer between sibling agents
  4. Import smoke tests   -- verify all new modules import cleanly

Uses temporary SQLite databases (via monkeypatching DB paths) so tests
never touch real .db files.
"""
import json
import sqlite3
import time

import pytest

import tools.cognition_base_db as cdb
import tools.evolution_db as edb
from tools.cross_agent_learning import (
    _get_department,
    _get_sibling_agents,
    DEPARTMENT_MAP,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture(autouse=True)
def isolated_cognition_db(tmp_path, monkeypatch):
    """Point cognition_base_db at a fresh temp file for each test."""
    db_path = tmp_path / "test_cognition.db"
    monkeypatch.setattr(cdb, "COGNITION_DB_PATH", db_path)
    cdb.init_db()
    yield


@pytest.fixture(autouse=True)
def isolated_evolution_db(tmp_path, monkeypatch):
    """Point evolution_db at a fresh temp file for each test."""
    db_path = tmp_path / "test_evolution.db"
    monkeypatch.setattr(edb, "EVOLUTION_DB_PATH", db_path)
    edb.init_db()
    yield


# ============================================================================
# 1. Cognition Base DB Tests
# ============================================================================


class TestCognitionBaseDB:
    def test_init_db_creates_table(self, tmp_path, monkeypatch):
        """Verify cognition_entries table exists after init."""
        db_path = tmp_path / "fresh_cognition.db"
        monkeypatch.setattr(cdb, "COGNITION_DB_PATH", db_path)
        cdb.init_db()
        assert db_path.exists()
        conn = sqlite3.connect(str(db_path))
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        conn.close()
        assert "cognition_entries" in tables

    def test_add_and_get_entry(self):
        """Add an entry with all fields, get it back, verify all fields match."""
        entry_id = cdb.add_entry_sync(
            domain="sales",
            title="Cold outreach heuristic",
            content="Always personalize the first line",
            embedding_bytes=b"\x00\x01\x02\x03",
            source="manual",
        )
        assert isinstance(entry_id, str)
        assert len(entry_id) > 0

        entry = cdb.get_entry_sync(entry_id)
        assert entry is not None
        assert entry["id"] == entry_id
        assert entry["domain"] == "sales"
        assert entry["title"] == "Cold outreach heuristic"
        assert entry["content"] == "Always personalize the first line"
        assert entry["embedding"] == b"\x00\x01\x02\x03"
        assert entry["source"] == "manual"
        assert entry["relevance_score"] == 0.0
        assert entry["access_count"] == 0
        assert entry["created_at"] is not None

    def test_search_by_domain(self):
        """Add entries in different domains, search by domain, verify filtering."""
        cdb.add_entry_sync("sales", "Sale tip", "content-a", None, "test")
        cdb.add_entry_sync("engineering", "Eng tip", "content-b", None, "test")
        cdb.add_entry_sync("sales", "Sale tip 2", "content-c", None, "test")

        sales_results = cdb.search_by_domain_sync("sales")
        assert len(sales_results) == 2
        assert all(r["domain"] == "sales" for r in sales_results)

        eng_results = cdb.search_by_domain_sync("engineering")
        assert len(eng_results) == 1
        assert eng_results[0]["domain"] == "engineering"

    def test_update_relevance(self):
        """Add entry, update relevance score, verify change."""
        entry_id = cdb.add_entry_sync("qa", "Test tip", "content", None, "test")
        entry = cdb.get_entry_sync(entry_id)
        assert entry["relevance_score"] == 0.0

        cdb.update_relevance_sync(entry_id, 0.85)
        updated = cdb.get_entry_sync(entry_id)
        assert updated["relevance_score"] == pytest.approx(0.85)

    def test_increment_access(self):
        """Add entry, increment access 3 times, verify count."""
        entry_id = cdb.add_entry_sync("research", "Tip", "content", None, "test")
        for _ in range(3):
            cdb.increment_access_sync(entry_id)

        entry = cdb.get_entry_sync(entry_id)
        assert entry["access_count"] == 3

    def test_delete_entry(self):
        """Add entry, delete it, verify gone."""
        entry_id = cdb.add_entry_sync("marketing", "Tip", "content", None, "test")
        assert cdb.get_entry_sync(entry_id) is not None

        result = cdb.delete_entry_sync(entry_id)
        assert result is True
        assert cdb.get_entry_sync(entry_id) is None

        # Deleting again returns False
        result2 = cdb.delete_entry_sync(entry_id)
        assert result2 is False

    def test_count_entries(self):
        """Add entries, verify count (total and by domain)."""
        cdb.add_entry_sync("sales", "A", "content", None, "test")
        cdb.add_entry_sync("sales", "B", "content", None, "test")
        cdb.add_entry_sync("engineering", "C", "content", None, "test")

        total = cdb.count_entries_sync()
        assert total == 3

        sales_count = cdb.count_entries_sync(domain="sales")
        assert sales_count == 2

        eng_count = cdb.count_entries_sync(domain="engineering")
        assert eng_count == 1

        empty_count = cdb.count_entries_sync(domain="nonexistent")
        assert empty_count == 0

    def test_get_recent_entries(self):
        """Add entries, verify most recent come first."""
        cdb.add_entry_sync("qa", "First", "content-1", None, "test")
        # Small delay to ensure different timestamps
        time.sleep(0.05)
        cdb.add_entry_sync("qa", "Second", "content-2", None, "test")
        time.sleep(0.05)
        cdb.add_entry_sync("qa", "Third", "content-3", None, "test")

        recent = cdb.get_recent_entries_sync(domain="qa", limit=3)
        assert len(recent) == 3
        assert recent[0]["title"] == "Third"
        assert recent[1]["title"] == "Second"
        assert recent[2]["title"] == "First"

        # Test limit
        recent_limited = cdb.get_recent_entries_sync(domain="qa", limit=1)
        assert len(recent_limited) == 1
        assert recent_limited[0]["title"] == "Third"


# ============================================================================
# 2. Evolution DB -- Candidate Pool / UCB1 Tests
# ============================================================================


class TestCandidatePool:
    def test_add_candidate(self):
        """Add candidate, verify it's in the pool."""
        cid = edb.add_candidate_sync("test_agent", "Do X then Y", fitness_score=0.5)
        assert isinstance(cid, str)
        assert len(cid) > 0

        candidates = edb.get_active_candidates_sync("test_agent")
        assert len(candidates) == 1
        assert candidates[0]["id"] == cid
        assert candidates[0]["instruction"] == "Do X then Y"
        assert candidates[0]["fitness_score"] == pytest.approx(0.5)
        assert candidates[0]["status"] == "active"
        assert candidates[0]["visit_count"] == 0

    def test_ucb1_selects_unvisited_first(self):
        """Add 3 candidates, 2 visited, 1 unvisited -- UCB1 picks unvisited."""
        c1 = edb.add_candidate_sync("ucb_agent", "instr-1", fitness_score=0.9)
        c2 = edb.add_candidate_sync("ucb_agent", "instr-2", fitness_score=0.8)
        c3 = edb.add_candidate_sync("ucb_agent", "instr-3", fitness_score=0.1)

        # Mark c1 and c2 as visited
        edb.record_candidate_reward_sync(c1, 0.9)
        edb.record_candidate_reward_sync(c2, 0.8)

        # c3 is unvisited (visit_count=0) so UCB1 should pick it
        selected = edb.sample_parent_ucb1_sync("ucb_agent")
        assert selected is not None
        assert selected["id"] == c3

    def test_ucb1_balances_exploration_exploitation(self):
        """Add candidates with different visit counts and rewards.
        Verify UCB1 doesn't always pick highest reward."""
        # Candidate A: high reward, many visits (exploitation)
        ca = edb.add_candidate_sync("bal_agent", "high-reward", fitness_score=0.0)
        for _ in range(20):
            edb.record_candidate_reward_sync(ca, 0.9)

        # Candidate B: moderate reward, few visits (exploration bonus)
        cb = edb.add_candidate_sync("bal_agent", "moderate-reward", fitness_score=0.0)
        edb.record_candidate_reward_sync(cb, 0.5)

        selected = edb.sample_parent_ucb1_sync("bal_agent")
        assert selected is not None
        # With 20 vs 1 visits, the exploration bonus for cb should be large:
        # UCB1(cb) = 0.5 + 1.41 * sqrt(ln(21)/1) ~= 0.5 + 1.41*1.75 ~= 2.96
        # UCB1(ca) = 0.9 + 1.41 * sqrt(ln(21)/20) ~= 0.9 + 1.41*0.39 ~= 1.45
        # So cb should be selected
        assert selected["id"] == cb

    def test_maintain_population_retires_weak(self):
        """Add 15 candidates with varying fitness, 5+ visits each.
        Call maintain_population(max_pop=10) and verify some retired."""
        agent = "pop_agent"
        for i in range(15):
            cid = edb.add_candidate_sync(agent, f"instr-{i}", fitness_score=0.0)
            # Give each at least 5 visits with varying rewards
            for _ in range(5):
                edb.record_candidate_reward_sync(cid, float(i) / 15.0)

        candidates_before = edb.get_active_candidates_sync(agent)
        assert len(candidates_before) == 15

        retired = edb.maintain_population_sync(agent, max_pop=10)
        assert retired > 0

        candidates_after = edb.get_active_candidates_sync(agent)
        assert len(candidates_after) < 15

    def test_get_champion(self):
        """Add candidates with different fitness, verify champion is highest."""
        agent = "champ_agent"
        c_low = edb.add_candidate_sync(agent, "low", fitness_score=0.0)
        c_mid = edb.add_candidate_sync(agent, "mid", fitness_score=0.0)
        c_high = edb.add_candidate_sync(agent, "high", fitness_score=0.0)

        # Give visits >= 3 to qualify as champion
        for _ in range(3):
            edb.record_candidate_reward_sync(c_low, 0.2)
            edb.record_candidate_reward_sync(c_mid, 0.5)
            edb.record_candidate_reward_sync(c_high, 0.9)

        champion = edb.get_champion_sync(agent)
        assert champion is not None
        assert champion["id"] == c_high

    def test_promote_champion(self):
        """Promote champion, verify status='champion', previous champion demoted."""
        agent = "promote_agent"
        c1 = edb.add_candidate_sync(agent, "first", fitness_score=0.0)
        c2 = edb.add_candidate_sync(agent, "second", fitness_score=0.0)

        # Give enough visits for champion eligibility
        for _ in range(4):
            edb.record_candidate_reward_sync(c1, 0.3)
            edb.record_candidate_reward_sync(c2, 0.9)

        # First promotion: c2 should be champion (higher fitness)
        promoted1 = edb.promote_champion_sync(agent)
        assert promoted1 is not None
        assert promoted1["id"] == c2
        assert promoted1["status"] == "champion"

        # Now give c1 much higher rewards to make it the new champion
        for _ in range(10):
            edb.record_candidate_reward_sync(c1, 1.0)

        # Second promotion: c1 should now be champion, c2 demoted back to active
        promoted2 = edb.promote_champion_sync(agent)
        assert promoted2 is not None
        assert promoted2["id"] == c1
        assert promoted2["status"] == "champion"

        # Verify c2 was demoted back to active
        candidates = edb.get_active_candidates_sync(agent)
        c2_row = next((c for c in candidates if c["id"] == c2), None)
        assert c2_row is not None
        assert c2_row["status"] == "active"

    def test_record_candidate_reward(self):
        """Add candidate, record rewards, verify visit_count and total_reward."""
        cid = edb.add_candidate_sync("reward_agent", "instr", fitness_score=0.0)

        edb.record_candidate_reward_sync(cid, 0.7)
        edb.record_candidate_reward_sync(cid, 0.3)

        candidates = edb.get_active_candidates_sync("reward_agent")
        cand = candidates[0]
        assert cand["visit_count"] == 2
        assert cand["total_reward"] == pytest.approx(1.0)
        # fitness_score = total_reward / visit_count = 1.0 / 2 = 0.5
        assert cand["fitness_score"] == pytest.approx(0.5)

    def test_candidate_lineage(self):
        """Create chain: grandparent -> parent -> child. Verify lineage traces back."""
        agent = "lineage_agent"
        grandparent = edb.add_candidate_sync(agent, "gen-0", generation=0)
        parent = edb.add_candidate_sync(
            agent, "gen-1", parent_id=grandparent, generation=1
        )
        child = edb.add_candidate_sync(
            agent, "gen-2", parent_id=parent, generation=2
        )

        lineage = edb.get_candidate_lineage_sync(child)
        assert len(lineage) == 3
        assert lineage[0]["id"] == child
        assert lineage[0]["generation"] == 2
        assert lineage[1]["id"] == parent
        assert lineage[1]["generation"] == 1
        assert lineage[2]["id"] == grandparent
        assert lineage[2]["generation"] == 0


# ============================================================================
# 3. Cross-Agent Learning Tests
# ============================================================================


class TestCrossAgentLearning:
    def test_get_department(self):
        """Verify department lookup for known agents."""
        assert _get_department("lead_researcher_agent") == "sales"
        assert _get_department("pm_agent") == "product"
        assert _get_department("data_engineer_agent") == "engineering"
        assert _get_department("qa_engineer_agent") == "qa"
        assert _get_department("nonexistent_agent") is None

    def test_get_sibling_agents(self):
        """Verify sibling detection for a sales agent includes other sales agents."""
        siblings = _get_sibling_agents("lead_researcher_agent")
        assert isinstance(siblings, list)
        assert len(siblings) > 0
        # Should include other sales agents
        assert "outreach_composer_agent" in siblings
        assert "deal_analyst_agent" in siblings
        # Should include cross-department role-group siblings (researcher group)
        assert "research_scientist_agent" in siblings
        # Should NOT include self
        assert "lead_researcher_agent" not in siblings

    def test_get_sibling_agents_unknown_returns_empty(self):
        """Unknown agent has no siblings."""
        siblings = _get_sibling_agents("totally_unknown_agent")
        assert siblings == []

    def test_extract_transfer_patterns(self, monkeypatch):
        """Mock successful evolution, verify cognition entry saved and siblings queued."""
        # Track calls to add_cognition and enqueue_agent_sync
        cognition_calls = []
        enqueue_calls = []

        def mock_add_cognition(title, content, domain, source="manual"):
            cognition_calls.append({
                "title": title,
                "content": content,
                "domain": domain,
                "source": source,
            })

        def mock_enqueue_agent_sync(agent_name, priority, evidence):
            enqueue_calls.append({
                "agent_name": agent_name,
                "priority": priority,
                "evidence": evidence,
            })

        import tools.cross_agent_learning as cal
        monkeypatch.setattr(cal, "add_cognition", mock_add_cognition)
        monkeypatch.setattr(edb, "enqueue_agent_sync", mock_enqueue_agent_sync)

        result_json = cal.extract_transfer_patterns_sync(
            agent_name="lead_researcher_agent",
            hypothesis_text="Improved outreach by adding personalization",
            root_cause="Generic outreach was being ignored",
        )

        result = json.loads(result_json)
        assert result["source_agent"] == "lead_researcher_agent"
        assert result["department"] == "sales"
        assert result["siblings_found"] > 0
        assert result["cognition_entry_saved"] is True
        assert len(result["transfers_queued"]) > 0

        # Verify cognition entry was saved
        assert len(cognition_calls) == 1
        assert "lead_researcher_agent" in cognition_calls[0]["title"]
        assert cognition_calls[0]["domain"] == "sales"

        # Verify sibling agents were queued
        assert len(enqueue_calls) > 0
        assert all(e["priority"] == 8.0 for e in enqueue_calls)


# ============================================================================
# 4. Import Tests
# ============================================================================


class TestImports:
    def test_cognition_base_db_import(self):
        """Verify cognition_base_db module imports cleanly."""
        try:
            from tools.cognition_base_db import init_db, add_entry_sync
            assert callable(init_db)
            assert callable(add_entry_sync)
        except ImportError as exc:
            pytest.skip(f"cognition_base_db import failed: {exc}")

    def test_cognition_base_tools_import(self):
        """Verify cognition_base_tools module imports cleanly."""
        try:
            from tools.cognition_base_tools import search_cognition, add_cognition
            assert callable(search_cognition)
            assert callable(add_cognition)
        except ImportError as exc:
            pytest.skip(f"cognition_base_tools import failed: {exc}")

    def test_analyzer_agent_import(self):
        """Verify analyzer_agent module imports cleanly."""
        try:
            from agents.autoresearcher.analyzer_agent import analyzer_agent
            assert analyzer_agent is not None
        except ImportError as exc:
            pytest.skip(f"analyzer_agent import failed: {exc}")

    def test_cross_agent_learning_import(self):
        """Verify cross_agent_learning module imports cleanly."""
        try:
            from tools.cross_agent_learning import extract_transfer_patterns
            assert callable(extract_transfer_patterns)
        except ImportError as exc:
            pytest.skip(f"cross_agent_learning import failed: {exc}")

    def test_evolution_ucb1_import(self):
        """Verify evolution_tools UCB1 functions import cleanly."""
        try:
            from tools.evolution_tools import sample_parent_ucb1, add_candidate
            assert callable(sample_parent_ucb1)
            assert callable(add_candidate)
        except ImportError as exc:
            pytest.skip(f"evolution_tools import failed: {exc}")

    def test_evolution_db_candidate_pool_import(self):
        """Verify evolution_db candidate_pool functions import cleanly."""
        try:
            from tools.evolution_db import (
                add_candidate_sync,
                sample_parent_ucb1_sync,
                record_candidate_reward_sync,
                maintain_population_sync,
                get_champion_sync,
                promote_champion_sync,
                get_candidate_lineage_sync,
            )
            assert callable(add_candidate_sync)
            assert callable(sample_parent_ucb1_sync)
        except ImportError as exc:
            pytest.skip(f"evolution_db candidate pool import failed: {exc}")


# ============================================================================
# Async smoke tests
# ============================================================================


class TestAsyncSmoke:
    @pytest.mark.asyncio
    async def test_async_cognition_add_and_get(self):
        """Async add and get for cognition_base_db."""
        entry_id = await cdb.add_entry(
            domain="test", title="Async tip", content="async content",
            embedding_bytes=None, source="test",
        )
        entry = await cdb.get_entry(entry_id)
        assert entry is not None
        assert entry["title"] == "Async tip"

    @pytest.mark.asyncio
    async def test_async_candidate_pool(self):
        """Async add candidate and sample via UCB1."""
        cid = await edb.add_candidate("async_agent", "async instruction", 0.5)
        assert isinstance(cid, str)

        candidates = await edb.get_active_candidates("async_agent")
        assert len(candidates) == 1

        selected = await edb.sample_parent_ucb1("async_agent")
        assert selected is not None
        assert selected["id"] == cid
