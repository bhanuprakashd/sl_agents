"""
Integration tests for the intelligence pipeline.

Tests the FULL data flow across components:
  Skill Memory → Pre-build Quality Context → Build Prompts → AI Critique →
  Feedback Analysis → Improvement Plan → Rebuild Prompt → Meta-learning

These tests verify that intelligence actually FLOWS between layers,
not just that each layer works in isolation.
"""
import json
import os
import pytest


@pytest.fixture(autouse=True)
def _temp_db(tmp_path):
    """Point all DB operations to a temporary database."""
    db_path = str(tmp_path / "test_pipeline.db")
    os.environ["PRODUCT_DB_PATH"] = db_path
    yield db_path
    os.environ.pop("PRODUCT_DB_PATH", None)


# ── Full Pipeline: Skill Save → Retrieve → Quality Context ──────

class TestSkillLearningPipeline:
    """A build completes → skill saved → next similar build gets smart context."""

    def test_build_outcome_becomes_future_intelligence(self):
        """
        Simulate: build a shrimp farm app → save skill with feedback →
        next farm app should get pitfall warnings injected into prompts.
        """
        from tools.skill_memory import save_learned_skill, find_similar_skills
        from tools.human_feedback_loop import (
            save_feedback_round, get_prebuild_quality_context,
        )

        # Step 1: First product is built, had visual_ui feedback issues
        save_feedback_round(
            product_id="shrimp-v1",
            round_number=1,
            raw_feedback="the colors are ugly and the dashboard charts are hard to read",
            parsed_issues=[
                {"category": "visual_ui", "description": "bad color scheme"},
                {"category": "visual_ui", "description": "chart readability"},
            ],
            inferred_gaps=[],
            self_critique=[],
            improvement_plan=[],
            build_output="rebuilt with new colors",
            user_sentiment="negative",
        )
        save_feedback_round(
            product_id="shrimp-v1",
            round_number=2,
            raw_feedback="looks good now",
            parsed_issues=[],
            inferred_gaps=[],
            self_critique=[],
            improvement_plan=[],
            build_output="",
            user_sentiment="approved",
        )

        # Step 2: Save the learned skill with feedback insights
        save_learned_skill(
            product_id="shrimp-v1",
            product_name="ShrimpGuard Dashboard",
            prd={
                "product_type": "dashboard",
                "one_liner": "Shrimp farming water quality monitoring",
                "core_features": [
                    {"name": "Water Quality Dashboard"},
                    {"name": "Pond Management"},
                    {"name": "Alert System"},
                ],
                "data_model": [{"name": "Pond"}, {"name": "WaterReading"}],
            },
            architecture={"stack": {"frontend": "react", "database": "sqlite"}},
            build_result={
                "status": "approved",
                "phases_completed": ["scaffold", "features", "polish"],
                "qa_results": [],
                "feedback": {"total_rounds": 2, "common_issues": {"visual_ui": 2}},
            },
        )

        # Step 3: New similar product — should get intelligence from shrimp-v1
        similar = json.loads(find_similar_skills(
            "FarmWatch Monitor",
            {"product_type": "dashboard", "one_liner": "livestock farm monitoring dashboard",
             "core_features": [{"name": "Health Dashboard"}, {"name": "Alert System"}]},
        ))
        assert len(similar["similar_skills"]) >= 1
        skill = similar["similar_skills"][0]
        assert skill["product_name"] == "ShrimpGuard Dashboard"
        assert skill["quality_score"] > 0

        # Step 4: Quality context should include pitfall warnings
        quality_ctx = get_prebuild_quality_context(
            "FarmWatch Monitor",
            '{"product_type": "dashboard", "one_liner": "livestock monitoring"}',
        )
        # Should mention past visual_ui issues as pitfalls
        assert "visual_ui" in quality_ctx or "Common Issues" in quality_ctx

    def test_quality_score_reflects_build_difficulty(self):
        """Builds that needed many feedback rounds get lower quality scores."""
        from tools.skill_memory import save_learned_skill, _compute_quality_score

        # Easy build: approved first try
        easy_result = {
            "status": "approved",
            "feedback": {"total_rounds": 0},
            "phases_failed": [],
            "phases_completed": ["scaffold", "features", "polish"],
        }
        # Hard build: 5 rounds, phase failure
        hard_result = {
            "status": "shipped_with_issues",
            "feedback": {"total_rounds": 5},
            "phases_failed": [{"phase": "polish", "error": "timeout"}],
            "phases_completed": ["scaffold", "features"],
        }

        easy_score = _compute_quality_score(easy_result)
        hard_score = _compute_quality_score(hard_result)

        assert easy_score > hard_score
        assert easy_score >= 85  # Easy build = excellent
        assert hard_score <= 60  # Hard build = needs improvement

    def test_meta_learning_updates_skill_quality(self):
        """After feedback loop, skill quality is adjusted."""
        from tools.skill_memory import (
            save_learned_skill, update_skill_quality_from_feedback,
        )

        # Save initial skill at default quality
        save_learned_skill(
            "meta-test-1", "Test App",
            {"core_features": [{"name": "Auth"}]},
            {"stack": {"frontend": "react"}},
            {"status": "shipped", "phases_completed": ["scaffold"], "qa_results": []},
            quality_score=70,
        )

        # Feedback loop completed quickly → quality should go up
        result = update_skill_quality_from_feedback("meta-test-1", {
            "status": "approved",
            "total_rounds": 1,
        })
        assert "→" in result


# ── Full Pipeline: Feedback → Analysis → Plan → Prompt ───────────

class TestFeedbackAnalysisPipeline:
    """Human feedback flows through all analysis layers into a targeted rebuild prompt."""

    def test_negative_feedback_flows_through_all_layers(self):
        """
        Feedback "the dashboard charts are ugly and the login is broken" should:
        1. Classify as negative
        2. Parse into visual_ui + functionality categories
        3. Infer broader design + form checks (dashboard-aware)
        4. Generate prioritized plan
        5. Produce targeted prompt with progressive urgency
        """
        from tools.human_feedback_loop import (
            classify_user_sentiment,
            parse_explicit_feedback,
            infer_implicit_gaps,
            generate_improvement_plan,
            build_targeted_prompt,
        )

        raw = "the dashboard charts are ugly and hard to read, also login form is broken"
        prd = '{"product_type": "dashboard", "one_liner": "analytics dashboard"}'

        # Layer 1: Sentiment
        sentiment = classify_user_sentiment(raw)
        assert sentiment == "negative"

        # Layer 2: Explicit parsing (polarity-aware)
        explicit = parse_explicit_feedback(raw)
        categories = {i["category"] for i in explicit}
        assert "visual_ui" in categories
        assert "functionality" in categories
        # Check severity — "broken" is critical
        func_issues = [i for i in explicit if i["category"] == "functionality"]
        assert any(i["severity"] == "critical" for i in func_issues)

        # Layer 3: Inference (dashboard-aware)
        inferred = infer_implicit_gaps(explicit, prd=prd)
        inferred_descs = " ".join(i["description"] for i in inferred)
        # Should get dashboard-specific checks (charts, data tables)
        assert any(
            kw in inferred_descs.lower()
            for kw in ["chart", "design system", "form", "navigation"]
        )

        # Layer 4: Improvement plan
        plan = generate_improvement_plan(explicit, inferred, [], [])
        assert len(plan) >= 2
        # functionality (critical) should be priority 1
        assert plan[0]["severity"] in ("critical", "high")

        # Layer 5: Targeted prompt with urgency
        prompt = build_targeted_prompt(plan, "http://localhost:3000", prd, round_number=4, max_rounds=5)
        assert "CRITICAL" in prompt or "LAST" in prompt
        assert "http://localhost:3000" in prompt
        assert "Do NOT recreate" in prompt

    def test_mixed_feedback_captures_both_signals(self):
        """'Header looks good but the table data is wrong' → mixed, parses the negative part."""
        from tools.human_feedback_loop import (
            classify_user_sentiment,
            parse_explicit_feedback,
        )

        raw = "the header looks good but the table data is wrong and missing columns"
        sentiment = classify_user_sentiment(raw)
        assert sentiment == "mixed"

        issues = parse_explicit_feedback(raw)
        # Should flag the negative part (wrong, missing)
        assert len(issues) >= 1
        assert any(i["severity"] in ("high", "critical", "medium") for i in issues)

    def test_approval_short_circuits(self):
        """Approval feedback should NOT generate improvement plans."""
        from tools.human_feedback_loop import (
            classify_user_sentiment,
            parse_explicit_feedback,
        )

        for approval in ["looks good", "LGTM", "ship it!", "approved", ""]:
            assert classify_user_sentiment(approval) == "approved"
            issues = parse_explicit_feedback(approval)
            # Should have zero or only benign issues
            critical = [i for i in issues if i["severity"] == "critical"]
            assert len(critical) == 0

    def test_escalation_across_rounds(self):
        """Issues that persist across rounds should be escalated in severity."""
        from tools.human_feedback_loop import (
            parse_explicit_feedback,
            generate_improvement_plan,
            save_feedback_round,
            get_feedback_history,
        )

        # Round 1: visual_ui issue at medium severity
        save_feedback_round(
            product_id="esc-test",
            round_number=1,
            raw_feedback="colors need work",
            parsed_issues=[{"category": "visual_ui", "description": "bad palette"}],
            inferred_gaps=[], self_critique=[], improvement_plan=[],
            build_output="", user_sentiment="negative",
        )

        # Round 2: same category comes back
        history = json.loads(get_feedback_history("esc-test"))
        prior_rounds = history["rounds"]

        explicit = [{"category": "visual_ui", "description": "still bad colors",
                      "severity": "medium", "source": "explicit"}]
        plan = generate_improvement_plan(explicit, [], [], prior_rounds)

        # Should be escalated to high (was medium, but recurring)
        assert plan[0]["severity"] == "high"


# ── AI Critique Integration ──────────────────────────────────────

class TestAiCritiqueIntegration:
    """AI critique reads project files and produces structured output."""

    def test_critique_reads_real_files(self, tmp_path, monkeypatch):
        """
        Create a realistic project structure, run AI critique,
        verify it reads the right files and produces structured output.
        """
        from tools.human_feedback_loop import run_ai_critique

        # Create a minimal project
        (tmp_path / "index.html").write_text(
            "<html><body><h1>Farm Dashboard</h1>"
            "<div id='charts'>TODO: add charts</div></body></html>"
        )
        (tmp_path / "app.js").write_text(
            "// Main app\nconst data = [];\n"
            "function renderDashboard() { /* TODO */ }\n"
        )
        (tmp_path / "styles.css").write_text(
            "body { background: #fff; }\nh1 { color: red; }\n"
        )

        # Mock Claude to return structured critique
        mock_output = (
            "ISSUE|high|content|high|index.html has TODO placeholder in charts div\n"
            "ISSUE|medium|functionality|medium|app.js renderDashboard is empty stub\n"
        )
        monkeypatch.setattr(
            "tools.claude_code_tools._run_claude",
            lambda *a, **kw: {"ok": True, "error": None, "output": mock_output},
        )

        prd = '{"product_type": "dashboard", "core_features": [{"name": "Charts"}]}'
        issues = run_ai_critique(str(tmp_path), prd, "http://localhost:3000")

        assert len(issues) == 2
        assert issues[0]["category"] == "content"
        assert issues[0]["confidence"] == "high"
        assert issues[1]["category"] == "functionality"

    def test_critique_with_human_feedback_context(self, tmp_path, monkeypatch):
        """When human feedback is provided, it's woven into the critique prompt."""
        from tools.human_feedback_loop import run_ai_critique

        (tmp_path / "index.html").write_text("<html><body>App</body></html>")

        captured_prompt = {}
        def mock_run(project_dir, prompt, timeout=300):
            captured_prompt["text"] = prompt
            return {"ok": True, "error": None, "output": "APPROVED|none|none|high|ok"}

        monkeypatch.setattr("tools.claude_code_tools._run_claude", mock_run)

        run_ai_critique(
            str(tmp_path),
            '{"product_type": "ecommerce"}',
            "http://localhost:3000",
            human_feedback="the checkout flow is confusing and cart doesn't persist",
        )

        prompt = captured_prompt["text"]
        # Should include human feedback
        assert "checkout flow is confusing" in prompt
        # Should include domain-specific focus for ecommerce
        assert "checkout" in prompt.lower() or "cart" in prompt.lower()


# ── Weighted Skill Matching ──────────────────────────────────────

class TestWeightedSkillMatching:
    """Domain-matched skills should rank higher than feature-only matches."""

    def test_domain_match_beats_feature_match(self):
        from tools.skill_memory import save_learned_skill, find_similar_skills

        # Skill A: same domain (agriculture), different features
        save_learned_skill(
            "skill-agri", "FarmTracker",
            {"product_type": "dashboard", "one_liner": "crop monitoring",
             "core_features": [{"name": "Soil Analysis"}, {"name": "Weather Alerts"}],
             "data_model": [{"name": "Crop"}, {"name": "Field"}]},
            {"stack": {"frontend": "react", "database": "postgres"}},
            {"status": "shipped", "phases_completed": ["scaffold"], "qa_results": []},
            quality_score=80,
        )

        # Skill B: different domain, overlapping feature names
        save_learned_skill(
            "skill-social", "SocialFeed",
            {"product_type": "social", "one_liner": "social network feed",
             "core_features": [{"name": "Dashboard"}, {"name": "Alert System"}],
             "data_model": [{"name": "User"}, {"name": "Post"}]},
            {"stack": {"frontend": "react", "database": "postgres"}},
            {"status": "shipped", "phases_completed": ["scaffold"], "qa_results": []},
            quality_score=80,
        )

        # Search for a new agriculture product
        results = json.loads(find_similar_skills(
            "PondGuard",
            {"product_type": "dashboard", "one_liner": "aquaculture pond monitoring",
             "core_features": [{"name": "Water Quality"}, {"name": "Alerts"}],
             "data_model": [{"name": "Pond"}]},
        ))

        skills = results["similar_skills"]
        assert len(skills) >= 1
        # Both match on tech:react + tech:postgres, but FarmTracker should
        # rank higher due to domain:agriculture match (3x weight)
        if len(skills) >= 2:
            names = [s["product_name"] for s in skills]
            assert names[0] == "FarmTracker"


# ── Product-Type-Aware Inference Integration ─────────────────────

class TestProductTypeInferenceIntegration:
    """Inference rules adapt to what the product actually IS."""

    def test_ecommerce_visual_issue_checks_product_images(self):
        from tools.human_feedback_loop import infer_implicit_gaps

        explicit = [{"category": "visual_ui", "description": "bad layout", "severity": "high"}]
        prd = '{"product_type": "shop", "one_liner": "online store with cart and checkout"}'
        inferred = infer_implicit_gaps(explicit, prd=prd)

        descs = " ".join(i["description"] for i in inferred)
        assert "product image" in descs.lower() or "design system" in descs.lower()

    def test_form_heavy_functionality_checks_validation(self):
        from tools.human_feedback_loop import infer_implicit_gaps

        explicit = [{"category": "functionality", "description": "form broken", "severity": "critical"}]
        prd = '{"one_liner": "registration wizard with multi-step form and survey"}'
        inferred = infer_implicit_gaps(explicit, prd=prd)

        descs = " ".join(i["description"] for i in inferred)
        assert "validation" in descs.lower() or "form" in descs.lower()


# ── File Reading Intelligence Integration ────────────────────────

class TestFileReadingIntegration:
    """Realistic project structures are read with correct priority."""

    def test_reads_realistic_nextjs_project(self, tmp_path):
        from tools.human_feedback_loop import _read_project_files

        # Create Next.js-like structure
        (tmp_path / "package.json").write_text('{"name": "my-app", "version": "1.0"}')
        src = tmp_path / "src" / "app"
        src.mkdir(parents=True)
        (src / "layout.tsx").write_text("export default function RootLayout({children}) { return <html>{children}</html> }")
        (src / "page.tsx").write_text("export default function Home() { return <h1>Welcome</h1> }")

        # Junk dirs should be skipped
        for junk in [".next", "node_modules", "dist"]:
            d = tmp_path / junk
            d.mkdir()
            (d / "chunk.js").write_text("var x=1;" * 1000)

        styles = tmp_path / "src"
        (styles / "globals.css").write_text("body { margin: 0; }")

        result = _read_project_files(str(tmp_path))

        # Should include real source files
        assert "layout.tsx" in result
        assert "page.tsx" in result
        assert "package.json" in result
        # Should NOT include junk
        assert "chunk.js" not in result

    def test_importance_ordering_is_correct(self, tmp_path):
        """Entry points should appear before utility files."""
        from tools.human_feedback_loop import _file_importance
        from pathlib import Path

        idx = _file_importance(tmp_path / "index.html", tmp_path)
        util = _file_importance(tmp_path / "src" / "utils" / "helpers.js", tmp_path)
        assert idx > util


# ── Build Pipeline Forward Context ───────────────────────────────

class TestBuildForwardContext:
    """Phase results should flow forward into subsequent phase prompts."""

    def test_build_review_improve_passes_context_forward(self, tmp_path, monkeypatch):
        """
        Verify that phase 2 prompt includes phase 1 outcome,
        and phase 3 prompt includes both phase 1 and 2 outcomes.
        """
        from tools.claude_code_tools import build_review_improve, CLAUDE_WORKS_ROOT

        monkeypatch.setattr("tools.claude_code_tools.CLAUDE_WORKS_ROOT", tmp_path)

        captured_prompts = []

        def mock_run(project_dir, prompt, timeout=900):
            captured_prompts.append(prompt)
            return {
                "ok": True,
                "error": None,
                "output": "Phase complete. Server running at http://localhost:3000",
            }

        monkeypatch.setattr("tools.claude_code_tools._run_claude", mock_run)

        build_review_improve(
            "test-proj",
            "Build scaffold",
            "Build features",
            "Polish UI",
        )

        # Phase 1 (scaffold) should NOT have "EXISTING project" prefix
        assert "EXISTING project" not in captured_prompts[0]

        # Phase 2 (features) should have context from phase 1
        assert "EXISTING project" in captured_prompts[1]
        assert "SCAFFOLD PHASE COMPLETED" in captured_prompts[1]

        # Phase 3 (polish) should have context from both
        assert "SCAFFOLD PHASE COMPLETED" in captured_prompts[2]
        assert "FEATURES PHASE COMPLETED" in captured_prompts[2]
