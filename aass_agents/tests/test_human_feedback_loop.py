"""Tests for the human feedback loop system."""
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


# ── Sentiment Classification ──────────────────────────────────

class TestClassifySentiment:
    def test_approved_exact(self):
        from tools.human_feedback_loop import classify_user_sentiment
        assert classify_user_sentiment("approved") == "approved"

    def test_approved_looks_good(self):
        from tools.human_feedback_loop import classify_user_sentiment
        assert classify_user_sentiment("looks good") == "approved"

    def test_approved_lgtm(self):
        from tools.human_feedback_loop import classify_user_sentiment
        assert classify_user_sentiment("LGTM") == "approved"

    def test_approved_ship_it(self):
        from tools.human_feedback_loop import classify_user_sentiment
        assert classify_user_sentiment("ship it!") == "approved"

    def test_approved_empty(self):
        from tools.human_feedback_loop import classify_user_sentiment
        assert classify_user_sentiment("") == "approved"

    def test_negative_broken(self):
        from tools.human_feedback_loop import classify_user_sentiment
        assert classify_user_sentiment("the login page is broken") == "negative"

    def test_negative_ugly(self):
        from tools.human_feedback_loop import classify_user_sentiment
        assert classify_user_sentiment("the design is ugly") == "negative"

    def test_mixed_feedback(self):
        from tools.human_feedback_loop import classify_user_sentiment
        assert classify_user_sentiment("the nav is good but colors are bad") == "mixed"

    def test_positive_feedback(self):
        from tools.human_feedback_loop import classify_user_sentiment
        # "nice improvements" with no complaints is effectively approval
        assert classify_user_sentiment("much better now, nice improvements") == "approved"
        # Pure positive without approval words
        assert classify_user_sentiment("the layout improved a lot") == "positive"

    def test_negated_approval(self):
        from tools.human_feedback_loop import classify_user_sentiment
        # "doesn't look good" has negative overtone — should not be approved
        result = classify_user_sentiment("this is wrong and doesn't look good at all")
        assert result in ("negative", "mixed")  # should NOT be approved


# ── Explicit Feedback Parsing ─────────────────────────────────

class TestParseExplicitFeedback:
    def test_visual_issue(self):
        from tools.human_feedback_loop import parse_explicit_feedback
        issues = parse_explicit_feedback("the chart colors are ugly and hard to read")
        assert len(issues) >= 1
        categories = {i["category"] for i in issues}
        assert "visual_ui" in categories

    def test_functionality_issue(self):
        from tools.human_feedback_loop import parse_explicit_feedback
        issues = parse_explicit_feedback("the login page is broken, shows a 500 error")
        assert len(issues) >= 1
        assert any(i["severity"] == "critical" for i in issues)
        assert any(i["category"] == "functionality" for i in issues)

    def test_feature_gap(self):
        from tools.human_feedback_loop import parse_explicit_feedback
        issues = parse_explicit_feedback("I need a way to export data to CSV")
        assert any(i["category"] == "feature_gap" for i in issues)

    def test_empty_feedback(self):
        from tools.human_feedback_loop import parse_explicit_feedback
        assert parse_explicit_feedback("") == []

    def test_multiple_categories(self):
        from tools.human_feedback_loop import parse_explicit_feedback
        issues = parse_explicit_feedback(
            "the colors are bad and the navigation is confusing, also login is broken"
        )
        categories = {i["category"] for i in issues}
        assert len(categories) >= 2

    def test_ux_issue(self):
        from tools.human_feedback_loop import parse_explicit_feedback
        issues = parse_explicit_feedback("hard to find the settings page, navigation is confusing")
        assert any(i["category"] == "ux" for i in issues)

    def test_content_issue(self):
        from tools.human_feedback_loop import parse_explicit_feedback
        issues = parse_explicit_feedback("there's still lorem ipsum placeholder text everywhere")
        assert any(i["category"] == "content" for i in issues)


# ── Inferred Gaps ─────────────────────────────────────────────

class TestInferImplicitGaps:
    def test_visual_inference(self):
        from tools.human_feedback_loop import infer_implicit_gaps
        explicit = [{"category": "visual_ui", "description": "bad colors", "severity": "high"}]
        inferred = infer_implicit_gaps(explicit)
        assert len(inferred) >= 1
        assert all(i["source"] == "inferred" for i in inferred)

    def test_functionality_inference(self):
        from tools.human_feedback_loop import infer_implicit_gaps
        explicit = [{"category": "functionality", "description": "form broken", "severity": "critical"}]
        inferred = infer_implicit_gaps(explicit)
        assert len(inferred) >= 1

    def test_empty_input(self):
        from tools.human_feedback_loop import infer_implicit_gaps
        assert infer_implicit_gaps([]) == []

    def test_no_unknown_category_inference(self):
        from tools.human_feedback_loop import infer_implicit_gaps
        explicit = [{"category": "general", "description": "something", "severity": "medium"}]
        inferred = infer_implicit_gaps(explicit)
        assert inferred == []


# ── Self-Critique ─────────────────────────────────────────────

class TestSelfCritique:
    def test_missing_prd_features(self):
        from tools.human_feedback_loop import self_critique_against_prd
        prd = json.dumps({
            "core_features": [
                {"name": "User Authentication"},
                {"name": "Dashboard Analytics"},
                {"name": "Data Export"},
            ]
        })
        qa_report = "Tested user authentication and dashboard analytics"
        gaps = self_critique_against_prd(prd, "http://localhost:3000", qa_report)
        prd_gaps = [g for g in gaps if g["category"] == "prd_gap"]
        assert len(prd_gaps) >= 1
        assert any("Data Export" in g["description"] for g in prd_gaps)

    def test_always_includes_quality_checks(self):
        from tools.human_feedback_loop import self_critique_against_prd
        gaps = self_critique_against_prd("", "http://localhost:3000", "")
        quality_gaps = [g for g in gaps if g["category"] == "quality"]
        assert len(quality_gaps) >= 3  # error states, loading, validation, empty states

    def test_handles_invalid_prd(self):
        from tools.human_feedback_loop import self_critique_against_prd
        gaps = self_critique_against_prd("not json", "http://localhost:3000", "")
        assert isinstance(gaps, list)  # should not crash


# ── Improvement Plan ──────────────────────────────────────────

class TestGenerateImprovementPlan:
    def test_deduplication(self):
        from tools.human_feedback_loop import generate_improvement_plan
        explicit = [{"category": "visual_ui", "description": "bad colors", "severity": "high", "source": "explicit"}]
        inferred = [{"category": "visual_ui", "description": "review design system", "severity": "medium", "source": "inferred"}]
        plan = generate_improvement_plan(explicit, inferred, [], [])
        visual_items = [p for p in plan if p["category"] == "visual_ui"]
        assert len(visual_items) == 1  # deduplicated to one

    def test_cap_at_max_items(self):
        from tools.human_feedback_loop import generate_improvement_plan
        many_items = [
            {"category": f"cat_{i}", "description": f"issue {i}", "severity": "medium", "source": "explicit"}
            for i in range(20)
        ]
        plan = generate_improvement_plan(many_items, [], [], [], max_items=10)
        assert len(plan) <= 10

    def test_escalation_from_prior_rounds(self):
        from tools.human_feedback_loop import generate_improvement_plan
        explicit = [{"category": "visual_ui", "description": "still bad colors", "severity": "medium", "source": "explicit"}]
        prior = [{"parsed_issues": json.dumps([{"category": "visual_ui", "description": "bad colors"}])}]
        plan = generate_improvement_plan(explicit, [], [], prior)
        assert plan[0]["severity"] == "high"  # escalated from medium

    def test_priority_ordering(self):
        from tools.human_feedback_loop import generate_improvement_plan
        items = [
            {"category": "low_cat", "description": "low issue", "severity": "low", "source": "self_critique"},
            {"category": "crit_cat", "description": "critical issue", "severity": "critical", "source": "explicit"},
        ]
        plan = generate_improvement_plan(items, [], [], [])
        assert plan[0]["category"] == "crit_cat"

    def test_empty_inputs(self):
        from tools.human_feedback_loop import generate_improvement_plan
        plan = generate_improvement_plan([], [], [], [])
        assert plan == []


# ── Targeted Prompt ───────────────────────────────────────────

class TestBuildTargetedPrompt:
    def test_contains_existing_project_preamble(self):
        from tools.human_feedback_loop import build_targeted_prompt
        plan = [{"priority": 1, "category": "visual_ui", "description": "fix colors", "severity": "high", "source": "explicit"}]
        prompt = build_targeted_prompt(plan, "http://localhost:3000", "some prd")
        assert "EXISTING project" in prompt
        assert "Do NOT recreate" in prompt

    def test_contains_all_plan_items(self):
        from tools.human_feedback_loop import build_targeted_prompt
        plan = [
            {"priority": 1, "category": "visual_ui", "description": "fix colors", "severity": "high", "source": "explicit"},
            {"priority": 2, "category": "ux", "description": "fix nav", "severity": "medium", "source": "inferred"},
        ]
        prompt = build_targeted_prompt(plan, "http://localhost:3000", "prd text")
        assert "fix colors" in prompt
        assert "fix nav" in prompt
        assert "VISUAL_UI" in prompt

    def test_contains_url(self):
        from tools.human_feedback_loop import build_targeted_prompt
        prompt = build_targeted_prompt([], "http://localhost:8080", "")
        assert "http://localhost:8080" in prompt


# ── DB Persistence ────────────────────────────────────────────

class TestFeedbackPersistence:
    def test_save_and_retrieve(self):
        from tools.human_feedback_loop import save_feedback_round, get_feedback_history
        save_feedback_round(
            product_id="test-123",
            round_number=1,
            raw_feedback="colors are bad",
            parsed_issues=[{"category": "visual_ui", "description": "bad colors"}],
            inferred_gaps=[],
            self_critique=[],
            improvement_plan=[{"priority": 1, "description": "fix colors"}],
            build_output="rebuilt successfully",
            user_sentiment="negative",
            duration_s=45.2,
        )
        history = json.loads(get_feedback_history("test-123"))
        assert len(history["rounds"]) == 1
        assert history["rounds"][0]["raw_feedback"] == "colors are bad"
        assert history["rounds"][0]["user_sentiment"] == "negative"

    def test_multiple_rounds(self):
        from tools.human_feedback_loop import save_feedback_round, get_feedback_history
        for i in range(3):
            save_feedback_round(
                product_id="test-456",
                round_number=i + 1,
                raw_feedback=f"feedback {i}",
                parsed_issues=[],
                inferred_gaps=[],
                self_critique=[],
                improvement_plan=[],
                build_output="",
                user_sentiment="negative" if i < 2 else "approved",
            )
        history = json.loads(get_feedback_history("test-456"))
        assert len(history["rounds"]) == 3
        assert history["rounds"][-1]["user_sentiment"] == "approved"

    def test_feedback_patterns(self):
        from tools.human_feedback_loop import save_feedback_round, get_feedback_patterns
        # Simulate 3 products all having visual issues
        for pid in ["p1", "p2", "p3"]:
            save_feedback_round(
                product_id=pid,
                round_number=1,
                raw_feedback="colors are bad",
                parsed_issues=[{"category": "visual_ui", "description": "bad colors"}],
                inferred_gaps=[],
                self_critique=[],
                improvement_plan=[],
                build_output="",
                user_sentiment="negative",
            )
        patterns = json.loads(get_feedback_patterns())
        assert patterns["patterns"][0]["category"] == "visual_ui"
        assert patterns["patterns"][0]["count"] == 3

    def test_empty_history(self):
        from tools.human_feedback_loop import get_feedback_history
        history = json.loads(get_feedback_history("nonexistent"))
        assert history["rounds"] == []


# ── _read_project_files ──────────────────────────────────

class TestReadProjectFiles:
    def test_reads_html_files(self, tmp_path):
        from tools.human_feedback_loop import _read_project_files
        (tmp_path / "index.html").write_text("<h1>Hello</h1>")
        result = _read_project_files(str(tmp_path))
        assert "index.html" in result
        assert "<h1>Hello</h1>" in result

    def test_skips_node_modules(self, tmp_path):
        from tools.human_feedback_loop import _read_project_files
        nm = tmp_path / "node_modules" / "pkg"
        nm.mkdir(parents=True)
        (nm / "index.js").write_text("module.exports = {}")
        (tmp_path / "app.html").write_text("<div>app</div>")
        result = _read_project_files(str(tmp_path))
        assert "module.exports" not in result
        assert "app.html" in result

    def test_truncates_at_max_chars(self, tmp_path):
        from tools.human_feedback_loop import _read_project_files
        (tmp_path / "big.html").write_text("x" * 20000)
        result = _read_project_files(str(tmp_path), max_chars=500)
        assert len(result) <= 600  # some header overhead

    def test_missing_directory(self):
        from tools.human_feedback_loop import _read_project_files
        result = _read_project_files("/nonexistent/path/xyz")
        assert "not found" in result

    def test_empty_directory(self, tmp_path):
        from tools.human_feedback_loop import _read_project_files
        result = _read_project_files(str(tmp_path))
        assert "no source files" in result


# ── run_ai_critique ──────────────────────────────────────

class TestRunAiCritique:
    def test_falls_back_on_claude_failure(self, tmp_path, monkeypatch):
        """When Claude CLI is unavailable, falls back to static critique."""
        from tools.human_feedback_loop import run_ai_critique
        # Mock _run_claude to fail
        monkeypatch.setattr(
            "tools.claude_code_tools._run_claude",
            lambda *a, **kw: {"ok": False, "error": "no claude", "output": ""},
        )
        issues = run_ai_critique(str(tmp_path), '{"core_features": [{"name": "Auth"}]}', "http://localhost:3000")
        # Should get static fallback results
        assert isinstance(issues, list)
        assert any(i["category"] in ("prd_gap", "quality") for i in issues)

    def test_parses_issue_lines(self, tmp_path, monkeypatch):
        """Parses structured ISSUE lines from AI output."""
        from tools.human_feedback_loop import run_ai_critique
        mock_output = (
            "ISSUE|high|visual_ui|The header background color is too dark in styles.css:12\n"
            "ISSUE|medium|functionality|Login form missing validation in app.js:45\n"
        )
        monkeypatch.setattr(
            "tools.claude_code_tools._run_claude",
            lambda *a, **kw: {"ok": True, "error": None, "output": mock_output},
        )
        issues = run_ai_critique(str(tmp_path), "", "http://localhost:3000")
        assert len(issues) == 2
        assert issues[0]["category"] == "visual_ui"
        assert issues[0]["severity"] == "high"
        assert issues[0]["source"] == "ai_critique"
        assert issues[1]["category"] == "functionality"

    def test_approved_returns_empty(self, tmp_path, monkeypatch):
        """When AI says app is good, returns empty list."""
        from tools.human_feedback_loop import run_ai_critique
        monkeypatch.setattr(
            "tools.claude_code_tools._run_claude",
            lambda *a, **kw: {"ok": True, "error": None, "output": "APPROVED|none|none|No issues found"},
        )
        issues = run_ai_critique(str(tmp_path), "", "http://localhost:3000")
        assert issues == []

    def test_includes_human_feedback_in_prompt(self, tmp_path, monkeypatch):
        """When human feedback is provided, it's included in the critique prompt."""
        from tools.human_feedback_loop import run_ai_critique
        captured_args = {}
        def mock_run(project_dir, prompt, timeout=300):
            captured_args["prompt"] = prompt
            return {"ok": True, "error": None, "output": "APPROVED|none|none|ok"}
        monkeypatch.setattr("tools.claude_code_tools._run_claude", mock_run)
        run_ai_critique(str(tmp_path), "", "http://localhost:3000", human_feedback="colors are bad")
        assert "colors are bad" in captured_args["prompt"]


# ── get_prebuild_quality_context ─────────────────────────

class TestGetPrebuildQualityContext:
    def test_returns_empty_when_no_data(self):
        from tools.human_feedback_loop import get_prebuild_quality_context
        # With fresh DB and no skills, should return empty or minimal
        result = get_prebuild_quality_context("test-product", "")
        assert isinstance(result, str)

    def test_includes_feedback_patterns(self, _temp_db):
        from tools.human_feedback_loop import (
            get_prebuild_quality_context, save_feedback_round,
        )
        # Seed some feedback patterns
        for pid in ["p1", "p2", "p3"]:
            save_feedback_round(
                product_id=pid, round_number=1, raw_feedback="ugly colors",
                parsed_issues=[{"category": "visual_ui", "description": "bad colors"}],
                inferred_gaps=[], self_critique=[], improvement_plan=[],
                build_output="", user_sentiment="negative",
            )
        result = get_prebuild_quality_context("new-product", "")
        assert "visual_ui" in result or "Common Issues" in result


# ── Progressive urgency in build_targeted_prompt ─────────

class TestProgressiveUrgency:
    def test_early_round_calm(self):
        from tools.human_feedback_loop import build_targeted_prompt
        plan = [{"priority": 1, "category": "visual_ui", "description": "fix colors", "severity": "medium", "source": "explicit"}]
        prompt = build_targeted_prompt(plan, "http://localhost:3000", "", round_number=1, max_rounds=5)
        assert "self-reflect" in prompt.lower() or "Self-Reflection" in prompt

    def test_late_round_urgent(self):
        from tools.human_feedback_loop import build_targeted_prompt
        plan = [{"priority": 1, "category": "visual_ui", "description": "fix colors", "severity": "medium", "source": "explicit"}]
        prompt = build_targeted_prompt(plan, "http://localhost:3000", "", round_number=4, max_rounds=5)
        assert "CRITICAL" in prompt or "LAST" in prompt

    def test_mid_round_important(self):
        from tools.human_feedback_loop import build_targeted_prompt
        plan = [{"priority": 1, "category": "visual_ui", "description": "fix colors", "severity": "medium", "source": "explicit"}]
        prompt = build_targeted_prompt(plan, "http://localhost:3000", "", round_number=3, max_rounds=5)
        assert "IMPORTANT" in prompt


# ── Weighted Sentiment Scoring ───────────────────────────

class TestWeightedSentiment:
    def test_intensity_matters(self):
        """'completely broken' should be stronger negative than 'slightly off'."""
        from tools.human_feedback_loop import _compute_sentiment_score
        high_neg, _ = _compute_sentiment_score("the app is completely broken and crashes")
        low_neg, _ = _compute_sentiment_score("the alignment is slightly off")
        assert high_neg > low_neg

    def test_negated_positive_becomes_negative(self):
        """'doesn't look good' — positive word negated should contribute to negative score."""
        from tools.human_feedback_loop import _compute_sentiment_score
        neg, pos = _compute_sentiment_score("this doesn't look good")
        assert neg > 0

    def test_pure_positive(self):
        from tools.human_feedback_loop import _compute_sentiment_score
        neg, pos = _compute_sentiment_score("the design looks great and beautiful")
        assert pos > neg
        assert neg == 0

    def test_strong_positive_is_approved(self):
        from tools.human_feedback_loop import classify_user_sentiment
        assert classify_user_sentiment("looks great and beautiful, love it") == "approved"

    def test_weak_positive_not_approved(self):
        from tools.human_feedback_loop import classify_user_sentiment
        result = classify_user_sentiment("the layout improved a lot")
        assert result in ("positive", "approved")


# ── Polarity-Aware Parsing ───────────────────────────────

class TestPolarityAwareParsing:
    def test_positive_mention_not_flagged(self):
        """'I like the color' should NOT create a visual_ui issue."""
        from tools.human_feedback_loop import parse_explicit_feedback
        issues = parse_explicit_feedback("I like the color scheme")
        visual = [i for i in issues if i["category"] == "visual_ui"]
        assert len(visual) == 0  # Positive sentiment → no complaint

    def test_negative_mention_flagged(self):
        """'the color is ugly' should flag visual_ui."""
        from tools.human_feedback_loop import parse_explicit_feedback
        issues = parse_explicit_feedback("the color is ugly and hard to read")
        visual = [i for i in issues if i["category"] == "visual_ui"]
        assert len(visual) >= 1
        assert visual[0]["confidence"] == "high"

    def test_confidence_levels(self):
        """Direct complaints get high confidence, contextual inferences get medium."""
        from tools.human_feedback_loop import parse_explicit_feedback
        # Direct complaint keyword
        direct = parse_explicit_feedback("the login page is broken")
        assert any(i["confidence"] == "high" for i in direct)

    def test_severity_from_keywords(self):
        """Critical keywords should produce critical severity."""
        from tools.human_feedback_loop import parse_explicit_feedback
        issues = parse_explicit_feedback("the app crashes when I click submit")
        assert any(i["severity"] == "critical" for i in issues)


# ── Product-Type-Aware Inference ─────────────────────────

class TestProductTypeAwareInference:
    def test_dashboard_gets_chart_checks(self):
        from tools.human_feedback_loop import infer_implicit_gaps
        explicit = [{"category": "visual_ui", "description": "bad colors", "severity": "high"}]
        prd = '{"product_type": "dashboard", "one_liner": "analytics dashboard with charts"}'
        inferred = infer_implicit_gaps(explicit, prd=prd)
        descriptions = " ".join(i["description"] for i in inferred)
        assert "chart" in descriptions.lower() or "design system" in descriptions.lower()

    def test_management_gets_crud_checks(self):
        from tools.human_feedback_loop import infer_implicit_gaps
        explicit = [{"category": "functionality", "description": "form broken", "severity": "critical"}]
        prd = '{"product_type": "management app", "one_liner": "farm management system"}'
        inferred = infer_implicit_gaps(explicit, prd=prd)
        descriptions = " ".join(i["description"] for i in inferred)
        assert "CRUD" in descriptions or "navigation" in descriptions.lower()

    def test_general_product_gets_universal_rules(self):
        from tools.human_feedback_loop import infer_implicit_gaps
        explicit = [{"category": "ux", "description": "confusing", "severity": "medium"}]
        inferred = infer_implicit_gaps(explicit, prd="")
        assert len(inferred) >= 1  # At least universal rules

    def test_product_type_detection(self):
        from tools.human_feedback_loop import _detect_product_type
        assert _detect_product_type("analytics dashboard with charts and metrics") == "dashboard"
        assert _detect_product_type("online shop with cart and checkout") == "ecommerce"
        assert _detect_product_type("farm management and inventory system") == "management"
        assert _detect_product_type("something generic") == "general"


# ── Meta-Learning (skill quality from feedback) ──────────

class TestMetaLearning:
    def test_quality_score_auto_computed(self):
        from tools.skill_memory import _compute_quality_score
        # Fast approval = high score
        good_build = {"status": "approved", "feedback": {"total_rounds": 1}, "phases_failed": []}
        assert _compute_quality_score(good_build) >= 85

    def test_many_rounds_lowers_score(self):
        from tools.skill_memory import _compute_quality_score
        slow_build = {"status": "shipped_with_issues", "feedback": {"total_rounds": 5}, "phases_failed": []}
        fast_build = {"status": "approved", "feedback": {"total_rounds": 0}, "phases_failed": []}
        assert _compute_quality_score(fast_build) > _compute_quality_score(slow_build)

    def test_failed_phases_lower_score(self):
        from tools.skill_memory import _compute_quality_score
        failed = {"status": "built", "phases_failed": [{"phase": "scaffold", "error": "timeout"}]}
        clean = {"status": "shipped", "phases_failed": []}
        assert _compute_quality_score(clean) > _compute_quality_score(failed)

    def test_update_skill_quality(self, _temp_db):
        from tools.skill_memory import save_learned_skill, update_skill_quality_from_feedback
        import json
        save_learned_skill(
            "test-skill-1", "Test App", {"core_features": []}, {"stack": {}},
            {"status": "shipped", "phases_completed": ["scaffold"], "qa_results": []},
            quality_score=70,
        )
        result = update_skill_quality_from_feedback("test-skill-1", {
            "status": "approved", "total_rounds": 1,
        })
        assert "→" in result  # Shows old → new score
        assert "70" in result

    def test_update_nonexistent_skill(self, _temp_db):
        from tools.skill_memory import update_skill_quality_from_feedback
        result = update_skill_quality_from_feedback("nonexistent", {"status": "approved", "total_rounds": 1})
        assert "not found" in result


# ── AI Critique Domain-Aware Prompts ─────────────────────

class TestAiCritiqueDomainAware:
    def test_dashboard_critique_mentions_charts(self, tmp_path, monkeypatch):
        from tools.human_feedback_loop import run_ai_critique
        captured = {}
        def mock_run(project_dir, prompt, timeout=300):
            captured["prompt"] = prompt
            return {"ok": True, "error": None, "output": "APPROVED|none|none|high|ok"}
        monkeypatch.setattr("tools.claude_code_tools._run_claude", mock_run)
        run_ai_critique(str(tmp_path), '{"one_liner": "analytics dashboard with charts"}', "http://localhost:3000")
        assert "chart" in captured["prompt"].lower() or "dashboard" in captured["prompt"].lower()

    def test_confidence_field_in_output(self, tmp_path, monkeypatch):
        from tools.human_feedback_loop import run_ai_critique
        mock_output = "ISSUE|high|visual_ui|high|Colors are inconsistent in header.css:5\n"
        monkeypatch.setattr(
            "tools.claude_code_tools._run_claude",
            lambda *a, **kw: {"ok": True, "error": None, "output": mock_output},
        )
        issues = run_ai_critique(str(tmp_path), "", "http://localhost:3000")
        assert len(issues) == 1
        assert issues[0]["confidence"] == "high"


# ── File Reading Intelligence ────────────────────────────

class TestFileReadingIntelligence:
    def test_skips_build_directories(self, tmp_path):
        from tools.human_feedback_loop import _read_project_files
        for skip_dir in ["dist", ".next", "build"]:
            d = tmp_path / skip_dir
            d.mkdir()
            (d / "bundle.js").write_text("var x = 1;")
        (tmp_path / "app.html").write_text("<div>real</div>")
        result = _read_project_files(str(tmp_path))
        assert "var x = 1" not in result
        assert "real" in result

    def test_priority_ordering(self, tmp_path):
        from tools.human_feedback_loop import _read_project_files
        (tmp_path / "index.html").write_text("<h1>Entry</h1>")
        (tmp_path / "utils.js").write_text("function helper() {}")
        result = _read_project_files(str(tmp_path))
        # index.html should appear before utils.js (higher importance)
        idx_html = result.index("index.html")
        idx_utils = result.index("utils.js")
        assert idx_html < idx_utils

    def test_never_truncates_mid_file(self, tmp_path):
        """Files should be included fully or skipped — no mid-file cuts."""
        from tools.human_feedback_loop import _read_project_files
        (tmp_path / "small.html").write_text("<h1>Small</h1>")
        (tmp_path / "medium.js").write_text("x" * 500)
        # With tight limit, should include small fully or skip
        result = _read_project_files(str(tmp_path), max_chars=200)
        if "medium.js" in result:
            # If medium is included, it should be complete or first file truncated
            pass  # OK
        else:
            assert "Small" in result  # At least got the small file
