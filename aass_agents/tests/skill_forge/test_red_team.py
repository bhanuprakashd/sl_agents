"""
Smoke tests for red_team_agent.

Verifies agent definition loads, instruction describes the 100-case
test structure, and the CI helper function is correct. Never calls LLM.
"""
import math
import pytest


def test_red_team_agent_imports():
    from agents.skill_forge.red_team_agent import red_team_agent
    assert red_team_agent.name == "red_team_agent"


def test_red_team_has_description():
    from agents.skill_forge.red_team_agent import red_team_agent
    assert "100" in red_team_agent.description


def test_red_team_instruction_mentions_100_cases():
    from agents.skill_forge.red_team_agent import INSTRUCTION
    assert "100" in INSTRUCTION


def test_red_team_instruction_mentions_distribution():
    from agents.skill_forge.red_team_agent import INSTRUCTION
    assert "40" in INSTRUCTION  # common
    assert "30" in INSTRUCTION  # edge
    assert "20" in INSTRUCTION  # adversarial
    assert "10" in INSTRUCTION  # regression


def test_red_team_instruction_mentions_battle_test_report():
    from agents.skill_forge.red_team_agent import INSTRUCTION
    assert "BattleTestReport" in INSTRUCTION


def test_red_team_instruction_mentions_ci():
    from agents.skill_forge.red_team_agent import INSTRUCTION
    assert "CI" in INSTRUCTION or "confidence" in INSTRUCTION.lower()


def test_red_team_has_compute_ci_tool():
    from agents.skill_forge.red_team_agent import red_team_agent, compute_ci_bounds
    assert compute_ci_bounds in red_team_agent.tools


def test_red_team_has_get_best_version_tool():
    from agents.skill_forge.red_team_agent import red_team_agent
    from tools.skill_forge_db import get_best_skill_version_sync
    assert get_best_skill_version_sync in red_team_agent.tools


def test_red_team_has_save_battle_test_tool():
    from agents.skill_forge.red_team_agent import red_team_agent
    from tools.skill_forge_db import save_battle_test_sync
    assert save_battle_test_sync in red_team_agent.tools


def test_red_team_has_no_sub_agents():
    from agents.skill_forge.red_team_agent import red_team_agent
    assert not red_team_agent.sub_agents


# ── CI helper tests ───────────────────────────────────────────────────────────

def test_compute_ci_bounds_pass_rate_09():
    from agents.skill_forge.red_team_agent import compute_ci_bounds
    result = compute_ci_bounds(0.90, 100)
    # With pass_rate=0.90 and n=100, margin = 1.96 * sqrt(0.09) = 0.0588
    # ci_lower ≈ 0.90 - 0.0588 = 0.8412
    assert result["ci_lower"] >= 0.80
    assert result["ci_upper"] <= 1.0
    assert result["ci_lower"] < result["ci_upper"]


def test_compute_ci_bounds_pass_rate_085():
    from agents.skill_forge.red_team_agent import compute_ci_bounds
    result = compute_ci_bounds(0.85, 100)
    assert result["ci_lower"] >= 0.78  # approximately 0.85 - 1.96*sqrt(0.1275/100)
    assert result["ci_upper"] <= 1.0


def test_compute_ci_bounds_pass_rate_1():
    from agents.skill_forge.red_team_agent import compute_ci_bounds
    result = compute_ci_bounds(1.0, 100)
    assert result["ci_lower"] == pytest.approx(1.0)
    assert result["ci_upper"] == pytest.approx(1.0)


def test_compute_ci_bounds_pass_rate_0():
    from agents.skill_forge.red_team_agent import compute_ci_bounds
    result = compute_ci_bounds(0.0, 100)
    assert result["ci_lower"] == pytest.approx(0.0)
    assert result["ci_upper"] == pytest.approx(0.0)


def test_compute_ci_bounds_zero_n():
    from agents.skill_forge.red_team_agent import compute_ci_bounds
    result = compute_ci_bounds(0.9, 0)
    assert result["ci_lower"] == 0.0
    assert result["ci_upper"] == 0.0


def test_compute_ci_formula_correctness():
    """Test the exact 95% CI formula from the spec."""
    from agents.skill_forge.red_team_agent import compute_ci_bounds
    pass_rate = 0.90
    n = 100
    z = 1.96
    margin = z * math.sqrt(pass_rate * (1 - pass_rate) / n)
    expected_lower = pass_rate - margin
    expected_upper = pass_rate + margin

    result = compute_ci_bounds(pass_rate, n)
    assert result["ci_lower"] == pytest.approx(expected_lower, abs=0.001)
    assert result["ci_upper"] == pytest.approx(expected_upper, abs=0.001)
