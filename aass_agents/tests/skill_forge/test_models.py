"""
Unit tests for agents/skill_forge/models.py

Tests CompositeScore calculation, dataclass immutability, and field correctness.
"""
import pytest
from dataclasses import FrozenInstanceError


def test_composite_score_formula():
    from agents.skill_forge.models import CompositeScore
    score = CompositeScore(
        correctness=10.0,
        robustness=10.0,
        instruction_clarity=10.0,
        domain_accuracy=10.0,
    )
    assert score.composite == pytest.approx(10.0)


def test_composite_score_weighted():
    from agents.skill_forge.models import CompositeScore
    score = CompositeScore(
        correctness=8.0,
        robustness=6.0,
        instruction_clarity=7.0,
        domain_accuracy=9.0,
    )
    expected = 0.35 * 8.0 + 0.25 * 6.0 + 0.20 * 7.0 + 0.20 * 9.0
    assert score.composite == pytest.approx(expected)


def test_composite_score_weights_sum_to_one():
    """Verify the weight coefficients sum to 1.0."""
    assert pytest.approx(0.35 + 0.25 + 0.20 + 0.20) == 1.0


def test_composite_score_with_zeros():
    from agents.skill_forge.models import CompositeScore
    score = CompositeScore(
        correctness=0.0,
        robustness=0.0,
        instruction_clarity=0.0,
        domain_accuracy=0.0,
    )
    assert score.composite == pytest.approx(0.0)


def test_composite_score_promotion_gate_satisfied():
    """A score that should pass the 8.5 composite gate."""
    from agents.skill_forge.models import CompositeScore
    score = CompositeScore(
        correctness=9.0,
        robustness=8.5,
        instruction_clarity=8.5,
        domain_accuracy=9.0,
    )
    assert score.composite >= 8.5


def test_composite_score_promotion_gate_not_satisfied():
    """A score that should NOT pass the 8.5 composite gate."""
    from agents.skill_forge.models import CompositeScore
    score = CompositeScore(
        correctness=7.0,
        robustness=6.0,
        instruction_clarity=8.0,
        domain_accuracy=7.5,
    )
    assert score.composite < 8.5


def test_composite_score_is_frozen():
    from agents.skill_forge.models import CompositeScore
    score = CompositeScore(
        correctness=8.0,
        robustness=7.0,
        instruction_clarity=8.0,
        domain_accuracy=8.0,
    )
    with pytest.raises(FrozenInstanceError):
        score.correctness = 10.0  # type: ignore[misc]


def test_task_spec_is_frozen():
    from agents.skill_forge.models import TaskSpec
    spec = TaskSpec(
        task_name="test",
        domain="testing",
        skill_type="analysis",
        success_definition="passes all tests",
        scope_boundaries="unit tests only",
        department="engineering",
        priority="high",
    )
    with pytest.raises(FrozenInstanceError):
        spec.task_name = "modified"  # type: ignore[misc]


def test_task_spec_optional_existing_skill_path():
    from agents.skill_forge.models import TaskSpec
    spec = TaskSpec(
        task_name="new skill",
        domain="domain",
        skill_type="writing",
        success_definition="success",
        scope_boundaries="scope",
        department="generated",
        priority="medium",
    )
    assert spec.existing_skill_path is None


def test_task_spec_with_existing_skill_path():
    from agents.skill_forge.models import TaskSpec
    spec = TaskSpec(
        task_name="upgrade skill",
        domain="domain",
        skill_type="writing",
        success_definition="success",
        scope_boundaries="scope",
        department="generated",
        priority="high",
        existing_skill_path="skills/writing/pitch-decks/SKILL.md",
    )
    assert spec.existing_skill_path == "skills/writing/pitch-decks/SKILL.md"


def test_research_bundle_is_frozen():
    from agents.skill_forge.models import ResearchBundle
    bundle = ResearchBundle(
        researcher_type="domain",
        findings={"key": "value"},
        citations=["source1"],
    )
    with pytest.raises(FrozenInstanceError):
        bundle.researcher_type = "benchmark"  # type: ignore[misc]


def test_critic_score_fields():
    from agents.skill_forge.models import CriticScore
    critic = CriticScore(
        critic_type="domain_expert",
        score=8.5,
        feedback="Excellent domain coverage.",
        suggestions=["Add more examples"],
    )
    assert critic.critic_type == "domain_expert"
    assert critic.score == pytest.approx(8.5)
    assert len(critic.suggestions) == 1


def test_battle_test_report_fields():
    from agents.skill_forge.models import BattleTestReport
    report = BattleTestReport(
        pass_rate=0.88,
        ci_lower=0.807,
        ci_upper=0.953,
        failure_breakdown={"common": 2, "edge": 5, "adversarial": 5, "regression": 0},
        failed_cases=["tc_002", "tc_015"],
        total_cases=100,
    )
    assert report.pass_rate == pytest.approx(0.88)
    assert report.total_cases == 100
    assert len(report.failed_cases) == 2


def test_staging_entry_fields():
    from agents.skill_forge.models import StagingEntry
    entry = StagingEntry(
        skill_id="sales-pitch-writing",
        name="VC Pitch Writing",
        domain="sales",
        department="generated",
        file_path="generated_skills/sales/vc-pitch-writing",
        composite_score=8.7,
        needs_review=False,
        production_runs=3,
    )
    assert entry.skill_id == "sales-pitch-writing"
    assert entry.production_runs == 3
    assert entry.needs_review is False


def test_expert_blueprint_is_frozen():
    from agents.skill_forge.models import ExpertBlueprint
    blueprint = ExpertBlueprint(
        constitutional_principles=["Always do X", "Prioritise Y"],
        gold_examples=[{"input": "a", "output": "b"}],
        failure_mode_catalog=["FAILURE: missing context"],
        success_criteria=["passes all 100 test cases"],
        domain_constraints=["never violate Z"],
    )
    with pytest.raises(FrozenInstanceError):
        blueprint.constitutional_principles = []  # type: ignore[misc]


def test_test_case_fields():
    from agents.skill_forge.models import TestCase
    tc = TestCase(
        case_id="tc_042",
        category="adversarial",
        input="conflicting input",
        expected_behavior="graceful handling",
        failure_signal="incorrect output",
        judge_rubric="correctness + domain_accuracy",
    )
    assert tc.case_id == "tc_042"
    assert tc.category == "adversarial"
