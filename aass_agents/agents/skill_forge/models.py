"""
Data Transfer Objects for the SKILL FORGE pipeline.

All dataclasses are frozen (immutable) to prevent hidden side-effects across
the multi-agent pipeline stages.
"""
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TaskSpec:
    task_name: str
    domain: str
    skill_type: str
    success_definition: str
    scope_boundaries: str
    department: str
    priority: str
    existing_skill_path: str | None = None


@dataclass(frozen=True)
class ResearchBundle:
    researcher_type: str  # "domain" | "benchmark" | "technique"
    findings: dict[str, Any]
    citations: list[str]


@dataclass(frozen=True)
class ExpertBlueprint:
    constitutional_principles: list[str]
    gold_examples: list[dict]
    failure_mode_catalog: list[str]
    success_criteria: list[str]
    domain_constraints: list[str]


@dataclass(frozen=True)
class CriticScore:
    critic_type: str  # "domain_expert" | "instruction_quality" | "edge_case"
    score: float      # 1-10
    feedback: str
    suggestions: list[str]


@dataclass(frozen=True)
class CompositeScore:
    correctness: float
    robustness: float
    instruction_clarity: float
    domain_accuracy: float

    @property
    def composite(self) -> float:
        return (
            0.35 * self.correctness
            + 0.25 * self.robustness
            + 0.20 * self.instruction_clarity
            + 0.20 * self.domain_accuracy
        )


@dataclass(frozen=True)
class TestCase:
    case_id: str
    category: str  # "common" | "edge" | "adversarial" | "regression"
    input: str
    expected_behavior: str
    failure_signal: str
    judge_rubric: str


@dataclass(frozen=True)
class BattleTestReport:
    pass_rate: float
    ci_lower: float
    ci_upper: float
    failure_breakdown: dict[str, int]
    failed_cases: list[str]
    total_cases: int


@dataclass(frozen=True)
class StagingEntry:
    skill_id: str
    name: str
    domain: str
    department: str
    file_path: str
    composite_score: float
    needs_review: bool
    production_runs: int
