"""
Smoke tests for promoter_agent.

Verifies agent definition loads, CI gate math is correct, and kappa
calculation works. Never calls the live LLM.
"""
import math
import pytest


def test_promoter_agent_imports():
    from agents.skill_forge.promoter_agent import promoter_agent
    assert promoter_agent.name == "promoter_agent"


def test_promoter_has_description():
    from agents.skill_forge.promoter_agent import promoter_agent
    assert promoter_agent.description
    assert "CI" in promoter_agent.description or "gate" in promoter_agent.description.lower()


def test_promoter_instruction_mentions_ci_gate():
    from agents.skill_forge.promoter_agent import INSTRUCTION
    assert "0.80" in INSTRUCTION


def test_promoter_instruction_mentions_kappa():
    from agents.skill_forge.promoter_agent import INSTRUCTION
    assert "kappa" in INSTRUCTION.lower() or "κ" in INSTRUCTION


def test_promoter_instruction_mentions_composite_gate():
    from agents.skill_forge.promoter_agent import INSTRUCTION
    assert "8.5" in INSTRUCTION


def test_promoter_instruction_mentions_generated_skills():
    from agents.skill_forge.promoter_agent import INSTRUCTION
    assert "generated_skills" in INSTRUCTION


def test_promoter_has_compute_gates_tool():
    from agents.skill_forge.promoter_agent import promoter_agent, compute_promotion_gates
    assert compute_promotion_gates in promoter_agent.tools


def test_promoter_has_write_skill_files_tool():
    from agents.skill_forge.promoter_agent import promoter_agent, write_skill_files
    assert write_skill_files in promoter_agent.tools


def test_promoter_has_stage_skill_tool():
    from agents.skill_forge.promoter_agent import promoter_agent
    from tools.skill_forge_db import stage_skill_sync
    assert stage_skill_sync in promoter_agent.tools


def test_promoter_has_no_sub_agents():
    from agents.skill_forge.promoter_agent import promoter_agent
    assert not promoter_agent.sub_agents


# ── CI gate math tests ────────────────────────────────────────────────────────

def test_ci_gate_passes_at_090():
    """pass_rate=0.90 → ci_lower should be >= 0.80."""
    from agents.skill_forge.promoter_agent import compute_promotion_gates
    result = compute_promotion_gates(
        pass_rate=0.90,
        composite_score=9.0,
        judge_scores=[9.0, 8.5, 9.0],
    )
    assert result["ci_lower"] >= 0.80
    assert result["gate_ci"] is True


def test_ci_gate_passes_at_095():
    from agents.skill_forge.promoter_agent import compute_promotion_gates
    result = compute_promotion_gates(
        pass_rate=0.95,
        composite_score=9.0,
        judge_scores=[9.0, 9.0, 9.0],
    )
    assert result["gate_ci"] is True


def test_ci_gate_fails_at_075():
    """pass_rate=0.75 → ci_lower < 0.80."""
    from agents.skill_forge.promoter_agent import compute_promotion_gates
    result = compute_promotion_gates(
        pass_rate=0.75,
        composite_score=9.0,
        judge_scores=[9.0, 9.0, 9.0],
    )
    assert result["ci_lower"] < 0.80
    assert result["gate_ci"] is False


def test_composite_gate_passes_at_85():
    from agents.skill_forge.promoter_agent import compute_promotion_gates
    result = compute_promotion_gates(
        pass_rate=0.90,
        composite_score=8.5,
        judge_scores=[8.5, 8.5, 8.5],
    )
    assert result["gate_composite"] is True


def test_composite_gate_fails_below_85():
    from agents.skill_forge.promoter_agent import compute_promotion_gates
    result = compute_promotion_gates(
        pass_rate=0.90,
        composite_score=8.4,
        judge_scores=[8.0, 8.0, 8.0],
    )
    assert result["gate_composite"] is False


def test_all_gates_pass():
    from agents.skill_forge.promoter_agent import compute_promotion_gates
    result = compute_promotion_gates(
        pass_rate=0.92,
        composite_score=9.0,
        judge_scores=[9.0, 8.8, 9.2],
    )
    assert result["gate_ci"] is True
    assert result["gate_composite"] is True
    assert result["all_gates_pass"] is True


def test_all_gates_fail_on_low_pass_rate():
    from agents.skill_forge.promoter_agent import compute_promotion_gates
    result = compute_promotion_gates(
        pass_rate=0.70,
        composite_score=7.0,
        judge_scores=[7.0, 6.0, 8.0],
    )
    assert result["all_gates_pass"] is False


def test_ci_bounds_are_valid_range():
    from agents.skill_forge.promoter_agent import compute_promotion_gates
    result = compute_promotion_gates(
        pass_rate=0.85,
        composite_score=8.8,
        judge_scores=[9.0, 9.0, 8.5],
    )
    assert 0.0 <= result["ci_lower"] <= result["ci_upper"] <= 1.0


def test_kappa_field_is_present():
    from agents.skill_forge.promoter_agent import compute_promotion_gates
    result = compute_promotion_gates(
        pass_rate=0.90,
        composite_score=9.0,
        judge_scores=[9.0, 9.0, 9.0],
    )
    assert "kappa" in result
    assert isinstance(result["kappa"], float)


def test_kappa_gate_high_agreement():
    """Three identical scores should produce high kappa."""
    from agents.skill_forge.promoter_agent import compute_promotion_gates
    result = compute_promotion_gates(
        pass_rate=0.90,
        composite_score=9.0,
        judge_scores=[9.0, 9.0, 9.0],
    )
    assert result["gate_kappa"] is True


def test_kappa_gate_low_agreement():
    """Scores spread across bins (low, medium, high) should produce low kappa."""
    from agents.skill_forge.promoter_agent import compute_promotion_gates
    result = compute_promotion_gates(
        pass_rate=0.90,
        composite_score=9.0,
        judge_scores=[3.0, 6.0, 9.0],  # one per bin
    )
    assert result["gate_kappa"] is False


def test_single_judge_score_returns_zero_kappa():
    from agents.skill_forge.promoter_agent import _cohen_kappa_three_judges
    assert _cohen_kappa_three_judges([9.0]) == pytest.approx(0.0)


def test_empty_judge_scores_returns_zero_kappa():
    from agents.skill_forge.promoter_agent import _cohen_kappa_three_judges
    assert _cohen_kappa_three_judges([]) == pytest.approx(0.0)
